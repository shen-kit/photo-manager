from __future__ import annotations

import hashlib
import imghdr
import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func
from sqlmodel import Field, Session, SQLModel, select

from app.core.auth import get_current_user
from app.core.database import engine, get_session
from app.models import Asset, AssetTag, Face, Person, Tag, User
from app.services.assets_media import (
    MEDIA_ORIGINALS_DIR,
    build_fast_variants,
    processed_asset_dir,
    should_generate_large_preview,
    should_generate_small_in_api,
    validate_supported_image,
)

router = APIRouter()
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)


class AssetIngestPathRequest(SQLModel):
    file_path: str


class TagSummary(SQLModel):
    id: int
    name: str
    path: str


class PersonSummary(SQLModel):
    id: UUID | None = None
    name: str | None = None


class FaceSummary(SQLModel):
    id: UUID
    person: PersonSummary | None = None


class AssetCollectionItem(SQLModel):
    id: UUID
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    tags: list[TagSummary] = Field(default_factory=list)
    faces: list[FaceSummary] = Field(default_factory=list)


class AssetListResponse(SQLModel):
    items: list[AssetCollectionItem]
    page: int
    page_size: int
    total: int


class AssetDetailResponse(SQLModel):
    id: UUID
    file_hash: str
    master_path: str
    mime_type: str
    captured_at: datetime | None = None
    captured_at_local: str | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    file_size_bytes: int | None = None
    blurhash: str | None = None
    exif_data: dict[str, Any] | None = None
    tags: list[TagSummary] = Field(default_factory=list)
    people: list[PersonSummary] = Field(default_factory=list)
    faces: list[FaceSummary] = Field(default_factory=list)
    large_preview_url: str
    created_at: datetime


class AssetIngestResponse(SQLModel):
    id: UUID
    file_hash: str
    master_path: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    tiny_thumbnail_url: str
    small_thumbnail_url: str
    large_preview_url: str
    blurhash: str | None = None
    queued_job: bool


class AssetUpdateRequest(SQLModel):
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool | None = None


def _coerce_relative_path(raw_path: str) -> str:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Absolute file paths must resolve within the originals library root",
            ) from exc
    else:
        relative = candidate

    normalized = Path(str(relative)).as_posix().lstrip("/")
    if normalized.startswith("../") or normalized == "..":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File path must stay within the library root")
    return normalized


def _resolve_original_path(relative_path: str) -> Path:
    resolved = (MEDIA_ORIGINALS_DIR / relative_path).resolve()
    try:
        resolved.relative_to(MEDIA_ORIGINALS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolved file path escapes the library root") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original file was not found")
    return resolved


def _guess_mime_type(path: Path, uploaded_content_type: str | None = None) -> str:
    if uploaded_content_type:
        return uploaded_content_type
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    detected = imghdr.what(path)
    return f"image/{detected}" if detected else "application/octet-stream"


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return str(request.base_url).rstrip("/") + f"/media/processed/assets/{asset_id}/{variant}.webp"


def _processed_asset_dir(asset_id: UUID) -> Path:
    return processed_asset_dir(asset_id)


def _active_asset_where() -> Any:
    return Asset.deleted_at.is_(None)


def _get_active_asset(session: Session, asset_id: UUID) -> Asset:
    asset = session.exec(select(Asset).where(Asset.id == asset_id, _active_asset_where())).first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


def _save_uploaded_file(upload: UploadFile) -> tuple[str, Path]:
    filename = Path(upload.filename or f"{uuid4().hex}.bin")
    suffix = filename.suffix.lower()
    now = datetime.now(timezone.utc)
    relative_path = Path("uploads") / now.strftime("%Y") / now.strftime("%m") / f"{uuid4().hex}{suffix}"
    destination = (MEDIA_ORIGINALS_DIR / relative_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with destination.open("wb") as target:
            upload.file.seek(0)
            shutil.copyfileobj(upload.file, target)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to persist uploaded file") from exc
    finally:
        upload.file.seek(0)

    return relative_path.as_posix(), destination


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generate_fast_artifacts(asset_id: UUID, original_path: Path, include_small: bool) -> None:
    try:
        blurhash_value = build_fast_variants(original_path, asset_id, include_small=include_small)
    except Exception:
        return

    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            return
        asset.blurhash = blurhash_value
        session.add(asset)
        session.commit()


async def _enqueue_asset_job(asset_id: UUID) -> bool:
    try:
        redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        try:
            await redis.enqueue_job("process_asset_metadata", str(asset_id))
        finally:
            await redis.aclose()
    except Exception:
        return False
    return True


def _build_tag_models(rows: list[dict[str, Any]] | None) -> list[TagSummary]:
    return [TagSummary.model_validate(row) for row in (rows or [])]


def _build_face_models(rows: list[dict[str, Any]] | None) -> list[FaceSummary]:
    faces: list[FaceSummary] = []
    for row in rows or []:
        person_id = row.get("person_id")
        person_name = row.get("person_name")
        faces.append(
            FaceSummary(
                id=row["id"],
                person=PersonSummary(id=person_id, name=person_name) if person_id or person_name else None,
            )
        )
    return faces


def _build_people_models(rows: list[dict[str, Any]] | None) -> list[PersonSummary]:
    unique_people: dict[UUID, PersonSummary] = {}
    for row in rows or []:
        person_id = row.get("person_id")
        if person_id is None or person_id in unique_people:
            continue
        unique_people[person_id] = PersonSummary(id=person_id, name=row.get("person_name"))
    return list(unique_people.values())


def _asset_relations_subqueries() -> tuple[Any, Any]:
    tags_subquery = (
        select(
            AssetTag.asset_id.label("asset_id"),
            func.json_agg(
                func.json_build_object(
                    "id",
                    Tag.id,
                    "name",
                    Tag.name,
                    "path",
                    Tag.path,
                )
            ).label("tags"),
        )
        .select_from(AssetTag)
        .join(Tag, Tag.id == AssetTag.tag_id)
        .group_by(AssetTag.asset_id)
        .subquery()
    )

    faces_subquery = (
        select(
            Face.asset_id.label("asset_id"),
            func.json_agg(
                func.json_build_object(
                    "id",
                    Face.id,
                    "person_id",
                    Person.id,
                    "person_name",
                    Person.name,
                )
            ).label("faces"),
        )
        .select_from(Face)
        .join(Person, Person.id == Face.person_id, isouter=True)
        .group_by(Face.asset_id)
        .subquery()
    )

    return tags_subquery, faces_subquery


@router.post("/ingest", response_model=AssetIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_asset(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetIngestResponse:
    resolved_relative_path: str | None = None
    source_path: Path | None = None
    uploaded_path: Path | None = None

    if file is not None:
        resolved_relative_path, source_path = _save_uploaded_file(file)
        uploaded_path = source_path
    else:
        if request.headers.get("content-type", "").startswith("application/json"):
            payload = AssetIngestPathRequest.model_validate(await request.json())
            file_path = payload.file_path
        if not file_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either file upload or file_path")
        resolved_relative_path = _coerce_relative_path(file_path)
        source_path = _resolve_original_path(resolved_relative_path)

    assert resolved_relative_path is not None
    assert source_path is not None

    file_hash = _compute_sha256(source_path)
    existing_asset = session.exec(select(Asset).where(Asset.file_hash == file_hash, _active_asset_where())).first()
    if existing_asset is not None:
        if uploaded_path is not None:
            uploaded_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset with the same file hash already exists")

    try:
        width, height = validate_supported_image(source_path)
    except ValueError:
        logger.warning("Rejecting unsupported asset during ingest: %s", source_path)
        if uploaded_path is not None:
            uploaded_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image file")

    asset = Asset(
        file_hash=file_hash,
        master_path=resolved_relative_path,
        mime_type=_guess_mime_type(source_path, file.content_type if file else None),
        width=width,
        height=height,
        has_large_preview=should_generate_large_preview(width, height),
        file_size_bytes=source_path.stat().st_size,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)

    include_small = should_generate_small_in_api(asset.mime_type, asset.file_size_bytes or 0)
    background_tasks.add_task(_generate_fast_artifacts, asset.id, source_path, include_small)
    queued_job = await _enqueue_asset_job(asset.id)

    return AssetIngestResponse(
        id=asset.id,
        file_hash=asset.file_hash,
        master_path=asset.master_path,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        tiny_thumbnail_url=_thumbnail_url(request, asset.id, "tiny"),
        small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
        large_preview_url=_thumbnail_url(request, asset.id, "large"),
        blurhash=asset.blurhash,
        queued_job=queued_job,
    )


@router.get("/", response_model=AssetListResponse)
def list_assets(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetListResponse:
    if page < 1 or page_size < 1 or page_size > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pagination parameters")

    tags_subquery, faces_subquery = _asset_relations_subqueries()
    total = session.exec(select(func.count()).select_from(Asset).where(_active_asset_where())).one()
    offset = (page - 1) * page_size

    statement = (
        select(
            Asset,
            tags_subquery.c.tags,
            faces_subquery.c.faces,
        )
        .where(_active_asset_where())
        .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
        .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
        .order_by(Asset.captured_at.desc().nullslast(), Asset.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    rows = session.exec(statement).all()
    items = [
        AssetCollectionItem(
            id=asset.id,
            captured_at=asset.captured_at,
            description=asset.description,
            is_favorite=asset.is_favorite,
            width=asset.width,
            height=asset.height,
            has_large_preview=asset.has_large_preview,
            small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
            tags=_build_tag_models(tags),
            faces=_build_face_models(faces),
        )
        for asset, tags, faces in rows
    ]
    return AssetListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{asset_id}", response_model=AssetDetailResponse)
def get_asset(
    asset_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetDetailResponse:
    tags_subquery, faces_subquery = _asset_relations_subqueries()

    statement = (
        select(
            Asset,
            tags_subquery.c.tags,
            faces_subquery.c.faces,
        )
        .where(Asset.id == asset_id, _active_asset_where())
        .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
        .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
    )
    row = session.exec(statement).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    asset, tags, faces = row
    return AssetDetailResponse(
        id=asset.id,
        file_hash=asset.file_hash,
        master_path=asset.master_path,
        mime_type=asset.mime_type,
        captured_at=asset.captured_at,
        captured_at_local=asset.captured_at_local,
        description=asset.description,
        is_favorite=asset.is_favorite,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        file_size_bytes=asset.file_size_bytes,
        blurhash=asset.blurhash,
        exif_data=asset.exif_data,
        tags=_build_tag_models(tags),
        people=_build_people_models(faces),
        faces=_build_face_models(faces),
        large_preview_url=_thumbnail_url(request, asset.id, "large"),
        created_at=asset.created_at,
    )


@router.patch("/{asset_id}", response_model=AssetDetailResponse)
def update_asset(
    asset_id: UUID,
    payload: AssetUpdateRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetDetailResponse:
    asset = _get_active_asset(session, asset_id)

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(asset, field_name, value)
    session.add(asset)
    session.commit()

    return get_asset(asset_id=asset_id, request=request, session=session, current_user=current_user)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    asset = _get_active_asset(session, asset_id)
    asset.deleted_at = datetime.now(timezone.utc)
    session.add(asset)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
