from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlmodel import Field, SQLModel

from app.core.auth import get_current_user
from app.models import Asset, User
from app.services.assets.browse import (
    DEFAULT_GRID_LIMIT,
    AssetBrowseService,
    AssetGridFilters,
    AssetGridRow,
    get_asset_browse_service,
)
from app.services.assets.preview import AssetPreviewService, normalize_preview_priority
from app.services.assets.service import AssetService, get_asset_service
from app.services.assets.urls import build_preview_url, build_thumbnail_url
from app.services.people.service import PeopleService, get_people_service
from app.services.tags.service import TagService, get_tag_service

router = APIRouter()


class AssetIngestPathRequest(SQLModel):
    file_path: str


class AssetGridItem(SQLModel):
    id: UUID
    mime_type: str
    media_kind: str
    captured_at: datetime | None = None
    timeline_day: date
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    blurhash: str | None = None


class AssetGridPageResponse(SQLModel):
    items: list[AssetGridItem]
    next_cursor: str | None = None
    has_more: bool


class TagSummary(SQLModel):
    id: int
    name: str
    slug: str
    path: str
    is_album: bool = False
    cover_asset_id: UUID | None = None


class PersonSummary(SQLModel):
    id: UUID | None = None
    name: str | None = None


class FaceSummary(SQLModel):
    id: UUID
    person: PersonSummary | None = None


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
    small_thumbnail_url: str
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


class AssetPreviewEnsureRequest(SQLModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=100)
    priority: str = "low"


class AssetTagBatchRequest(SQLModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=500)
    tag_ids: list[int] = Field(min_length=1, max_length=100)


class AssetTagBatchResponse(SQLModel):
    updated_count: int


class AssetPreviewEnsureItemResponse(SQLModel):
    asset_id: UUID
    status: str
    preview_url: str | None = None
    job_id: UUID | None = None
    error: str | None = None


class AssetPreviewEnsureResponse(SQLModel):
    items: list[AssetPreviewEnsureItemResponse]


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return build_thumbnail_url(str(request.base_url), asset_id, variant)


def _preview_url(request: Request, asset: Asset) -> str:
    return build_preview_url(str(request.base_url), asset)


def _parse_person_ids(raw_person_ids: str | None) -> tuple[UUID, ...]:
    if raw_person_ids is None or not raw_person_ids.strip():
        return ()
    values: list[UUID] = []
    for item in raw_person_ids.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            values.append(UUID(normalized))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="person_ids must be a comma-separated list of UUIDs",
            ) from exc
    unique_values: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return tuple(unique_values)


def _parse_tag_ids(raw_tag_ids: str | None) -> tuple[int, ...]:
    if raw_tag_ids is None or not raw_tag_ids.strip():
        return ()
    values: list[int] = []
    for item in raw_tag_ids.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            values.append(int(normalized))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tag_ids must be a comma-separated list of integers",
            ) from exc
    return tuple(dict.fromkeys(values))


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
        small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
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


def _build_grid_item(request: Request, row: AssetGridRow) -> AssetGridItem:
    return AssetGridItem(
        id=row.id,
        mime_type=row.mime_type,
        media_kind=row.media_kind,
        captured_at=row.captured_at,
        timeline_day=row.timeline_day,
        is_favorite=row.is_favorite,
        width=row.width,
        height=row.height,
        duration_seconds=row.duration_seconds,
        has_large_preview=row.has_large_preview,
        small_thumbnail_url=_thumbnail_url(request, row.id, "small"),
        blurhash=row.blurhash,
    )


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


@router.get("", response_model=AssetGridPageResponse, include_in_schema=False)
@router.get("/", response_model=AssetGridPageResponse)
def list_assets(
    request: Request,
    limit: int = Query(default=DEFAULT_GRID_LIMIT, ge=1, le=200),
    cursor: str | None = Query(default=None),
    media_kind: str | None = Query(default=None),
    month: date | None = Query(default=None),
    day: date | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    tag_ids: str | None = Query(default=None),
    browse_service: AssetBrowseService = Depends(get_asset_browse_service),
    people_service: PeopleService = Depends(get_people_service),
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> AssetGridPageResponse:
    del current_user
    parsed_tag_ids = tag_service.validate_tag_ids(list(_parse_tag_ids(tag_ids)))
    filters = AssetGridFilters(
        media_kind=media_kind,
        month=month,
        day=day,
        person_ids=tuple(
            people_service.validate_person_ids(list(_parse_person_ids(person_ids)))
        ),
        tag_ids=tuple(parsed_tag_ids),
    )
    page = browse_service.list_asset_grid_page(
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    return AssetGridPageResponse(
        items=[_build_grid_item(request, row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post("/previews/ensure", response_model=AssetPreviewEnsureResponse)
async def ensure_asset_previews(
    payload: AssetPreviewEnsureRequest,
    request: Request,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetPreviewEnsureResponse:
    del current_user
    try:
        priority = normalize_preview_priority(payload.priority)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    items = await AssetPreviewService(asset_service.session).ensure_previews(
        asset_ids=payload.asset_ids,
        base_url=str(request.base_url),
        priority=priority,
    )
    return AssetPreviewEnsureResponse(
        items=[
            AssetPreviewEnsureItemResponse(
                asset_id=item.asset_id,
                status=item.status,
                preview_url=item.preview_url,
                job_id=item.job_id,
                error=item.error,
            )
            for item in items
        ]
    )


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


@router.post("/{asset_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_asset_tag(
    asset_id: UUID,
    tag_id: int,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    tag_service.add_tag_to_asset(asset_id=asset_id, tag_id=tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{asset_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_asset_tag(
    asset_id: UUID,
    tag_id: int,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    tag_service.remove_tag_from_asset(asset_id=asset_id, tag_id=tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tags:batch-add", response_model=AssetTagBatchResponse)
def batch_add_asset_tags(
    payload: AssetTagBatchRequest,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> AssetTagBatchResponse:
    del current_user
    updated_count = tag_service.batch_add_tags(
        asset_ids=payload.asset_ids,
        tag_ids=payload.tag_ids,
    )
    return AssetTagBatchResponse(updated_count=updated_count)


@router.post("/tags:batch-remove", response_model=AssetTagBatchResponse)
def batch_remove_asset_tags(
    payload: AssetTagBatchRequest,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> AssetTagBatchResponse:
    del current_user
    updated_count = tag_service.batch_remove_tags(
        asset_ids=payload.asset_ids,
        tag_ids=payload.tag_ids,
    )
    return AssetTagBatchResponse(updated_count=updated_count)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: UUID,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    asset_service.delete_asset(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
