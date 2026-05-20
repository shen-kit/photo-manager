from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlmodel import Field, SQLModel

from app.core.auth import get_current_user
from app.models import Asset, User
from app.services.assets.media import (
    MEDIA_PROCESSED_DIR,
    is_supported_video_mime_type,
    processed_video_preview_path,
)
from app.services.assets.service import AssetService, get_asset_service

router = APIRouter()


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
    blurhash: str | None = None
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
    video_codec: str | None = None
    audio_codec: str | None = None
    duration_seconds: float | None = None
    preview_status: str | None = None
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
    video_codec: str | None = None
    audio_codec: str | None = None
    duration_seconds: float | None = None
    preview_status: str | None = None
    tiny_thumbnail_url: str
    small_thumbnail_url: str
    large_preview_url: str
    blurhash: str | None = None
    queued_job: bool


class AssetUpdateRequest(SQLModel):
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool | None = None


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return (
        str(request.base_url).rstrip("/")
        + f"/media/processed/assets/{asset_id}/{variant}.webp"
    )


def _original_asset_url(request: Request, master_path: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    normalized = master_path.lstrip("/")
    return f"{base_url}/media/originals/{normalized}"


def _detail_image_url(request: Request, asset: Asset) -> str:
    if is_supported_video_mime_type(asset.mime_type):
        relative_preview = (
            processed_video_preview_path(asset.id)
            .relative_to(MEDIA_PROCESSED_DIR)
            .as_posix()
        )
        return (
            str(request.base_url).rstrip("/") + f"/media/processed/{relative_preview}"
        )
    if asset.has_large_preview:
        return _thumbnail_url(request, asset.id, "large")
    return _original_asset_url(request, asset.master_path)


def _build_ingest_response(
    request: Request, asset: Asset, queued_job: bool
) -> AssetIngestResponse:
    return AssetIngestResponse(
        id=asset.id,
        file_hash=asset.file_hash,
        master_path=asset.master_path,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        duration_seconds=asset.duration_seconds,
        preview_status=asset.preview_status,
        tiny_thumbnail_url=_thumbnail_url(request, asset.id, "tiny"),
        small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
        large_preview_url=_detail_image_url(request, asset),
        blurhash=asset.blurhash,
        queued_job=queued_job,
    )


def _build_detail_response(
    request: Request,
    asset: Asset,
    tags: list[dict[str, Any]] | None,
    faces: list[dict[str, Any]] | None,
) -> AssetDetailResponse:
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
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        duration_seconds=asset.duration_seconds,
        preview_status=asset.preview_status,
        blurhash=asset.blurhash,
        exif_data=asset.exif_data,
        tags=_build_tag_models(tags),
        people=_build_people_models(faces),
        faces=_build_face_models(faces),
        large_preview_url=_detail_image_url(request, asset),
        created_at=asset.created_at,
    )


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
                person=PersonSummary(id=person_id, name=person_name)
                if person_id or person_name
                else None,
            )
        )
    return faces


def _build_people_models(rows: list[dict[str, Any]] | None) -> list[PersonSummary]:
    unique_people: dict[UUID, PersonSummary] = {}
    for row in rows or []:
        person_id = row.get("person_id")
        if person_id is None or person_id in unique_people:
            continue
        unique_people[person_id] = PersonSummary(
            id=person_id, name=row.get("person_name")
        )
    return list(unique_people.values())


@router.post(
    "/ingest", response_model=AssetIngestResponse, status_code=status.HTTP_201_CREATED
)
async def ingest_asset(
    payload: AssetIngestPathRequest,
    request: Request,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetIngestResponse:
    result = await asset_service.ingest_asset_path(payload.file_path, current_user.id)
    return _build_ingest_response(request, result.asset, result.queued_job)


@router.post(
    "/upload", response_model=AssetIngestResponse, status_code=status.HTTP_201_CREATED
)
async def upload_asset(
    response: Response,
    request: Request,
    file: UploadFile = File(...),
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetIngestResponse:
    result = await asset_service.upload_asset(file, current_user.id)
    if not result.created_new:
        response.status_code = status.HTTP_200_OK
    return _build_ingest_response(request, result.asset, result.queued_job)


@router.get("", response_model=AssetListResponse, include_in_schema=False)
@router.get("/", response_model=AssetListResponse)
def list_assets(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetListResponse:
    del current_user
    if page < 1 or page_size < 1 or page_size > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters",
        )

    total, rows = asset_service.list_assets(page=page, page_size=page_size)
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
            blurhash=asset.blurhash,
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
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetDetailResponse:
    del current_user
    asset, tags, faces = asset_service.get_asset_detail(asset_id)
    return _build_detail_response(request, asset, tags, faces)


@router.patch("/{asset_id}", response_model=AssetDetailResponse)
def update_asset(
    asset_id: UUID,
    payload: AssetUpdateRequest,
    request: Request,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetDetailResponse:
    del current_user
    updates = payload.model_dump(exclude_unset=True)
    asset, tags, faces = asset_service.update_asset(asset_id, updates)
    return _build_detail_response(request, asset, tags, faces)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: UUID,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    asset_service.delete_asset(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
