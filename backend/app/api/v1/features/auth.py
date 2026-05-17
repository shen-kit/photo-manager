from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.core.auth import get_current_user
from app.core.database import get_session
from app.core.security import (
    ACCESS_TOKEN_TTL,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User, utc_now
from sqlmodel import SQLModel


router = APIRouter()


class RegisterRequest(SQLModel):
    username: str
    password: str


class LoginRequest(SQLModel):
    username: str
    password: str


class UserResponse(SQLModel):
    id: str
    username: str
    is_active: bool


class AuthResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


def _validate_credentials(username: str, password: str) -> tuple[str, str]:
    normalized_username = username.strip()
    if len(normalized_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters",
        )
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    return normalized_username, password


def _issue_refresh_token(*, session: Session, user: User) -> str:
    raw_token = create_refresh_token()
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=utc_now() + REFRESH_TOKEN_TTL,
    )
    session.add(token_record)
    session.flush()
    return raw_token


def _set_refresh_cookie(
    *, request: Request, response: Response, refresh_token: str
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(*, request: Request, response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/api/v1/auth",
    )


def _build_auth_response(user: User) -> AuthResponse:
    access_token = create_access_token(user_id=user.id, username=user.username)
    return AuthResponse(
        access_token=access_token,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        user=UserResponse(
            id=str(user.id), username=user.username, is_active=user.is_active
        ),
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
def register(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    username, password = _validate_credentials(payload.username, payload.password)

    existing_user = session.exec(select(User).where(User.username == username)).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered",
        )

    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    session.flush()

    refresh_token = _issue_refresh_token(session=session, user=user)
    session.commit()
    session.refresh(user)

    _set_refresh_cookie(request=request, response=response, refresh_token=refresh_token)
    return _build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    user = session.exec(
        select(User).where(User.username == payload.username.strip())
    ).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    refresh_token = _issue_refresh_token(session=session, user=user)
    session.commit()

    _set_refresh_cookie(request=request, response=response, refresh_token=refresh_token)
    return _build_auth_response(user)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    token_hash = hash_refresh_token(raw_refresh_token)
    token_record = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).first()
    if (
        token_record is None
        or token_record.revoked_at is not None
        or token_record.expires_at <= utc_now()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = session.exec(select(User).where(User.id == token_record.user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    new_raw_refresh_token = create_refresh_token()
    new_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw_refresh_token),
        expires_at=utc_now() + REFRESH_TOKEN_TTL,
    )
    session.add(new_token_record)
    session.flush()

    token_record.revoked_at = utc_now()
    token_record.replaced_by_token_id = new_token_record.id
    session.add(token_record)
    session.commit()

    _set_refresh_cookie(
        request=request, response=response, refresh_token=new_raw_refresh_token
    )
    return _build_auth_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        token_hash = hash_refresh_token(raw_refresh_token)
        token_record = session.exec(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).first()
        if token_record is not None and token_record.revoked_at is None:
            token_record.revoked_at = utc_now()
            session.add(token_record)
            session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(request=request, response=response)
    return response


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        is_active=current_user.is_active,
    )
