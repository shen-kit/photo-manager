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
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Field, SQLModel

from app.core.auth import get_current_user
from app.models import Asset, User
from app.services.assets.preview import AssetPreviewService
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
    preview_url: str
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
    preview_url: str
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


def _preview_url(request: Request, asset: Asset) -> str:
    return str(request.base_url).rstrip("/") + f"/api/v1/assets/{asset.id}/preview"


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
        preview_url=_preview_url(request, asset),
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
        preview_url=_preview_url(request, asset),
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


@router.get("/{asset_id}/preview")
async def get_asset_preview(
    asset_id: UUID,
    session_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
):
    del current_user
    resolution = await AssetPreviewService(session_service.session).resolve_preview(
        asset_id
    )
    if resolution.file_path is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "queued" if resolution.queued else "processing"},
            headers={"Retry-After": "3"},
        )
    media_type = None
    if resolution.file_path.suffix == ".mp4":
        media_type = "video/mp4"
    elif resolution.file_path.suffix == ".webp":
        media_type = "image/webp"
    return FileResponse(resolution.file_path, media_type=media_type)


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
