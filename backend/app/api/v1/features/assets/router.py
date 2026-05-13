from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import aiofiles
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func
from sqlmodel import Field, SQLModel, Session, select

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models import Asset, AssetTag, Face, Person, Tag, User
from app.services.asset_service import AssetService, active_asset_where, get_asset_service
from app.services.assets_media import MEDIA_ORIGINALS_DIR

router = APIRouter()
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


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


class AssetScanResponse(SQLModel):
    scanned_files: int
    already_ingested: int
    enqueued_jobs: int


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return str(request.base_url).rstrip("/") + f"/media/processed/assets/{asset_id}/{variant}.webp"


def _original_asset_url(request: Request, master_path: str) -> str:
    return str(request.base_url).rstrip("/") + f"/media/originals/{master_path.lstrip('/')}"


def _detail_image_url(request: Request, asset: Asset) -> str:
    if asset.has_large_preview:
        return _thumbnail_url(request, asset.id, "large")
    return _original_asset_url(request, asset.master_path)


def _get_active_asset(session: Session, asset_id: UUID) -> Asset:
    asset = session.exec(select(Asset).where(Asset.id == asset_id, active_asset_where())).first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


async def _save_upload_to_originals(upload: UploadFile) -> Path:
    filename = Path(upload.filename or f"{uuid4().hex}.bin")
    suffix = filename.suffix.lower()
    now = datetime.now(timezone.utc)
    relative_path = Path("uploads") / now.strftime("%Y") / now.strftime("%m") / f"{uuid4().hex}{suffix}"
    destination = (MEDIA_ORIGINALS_DIR / relative_path).resolve()

    try:
        destination.relative_to(MEDIA_ORIGINALS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload destination escaped the originals root") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        await upload.seek(0)
        async with aiofiles.open(destination, "wb") as target:
            while chunk := await upload.read(1024 * 1024):
                await target.write(chunk)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to persist uploaded file") from exc
    finally:
        await upload.close()

    return destination


def _build_ingest_response(request: Request, asset: Asset, queued_job: bool) -> AssetIngestResponse:
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
        large_preview_url=_detail_image_url(request, asset),
        blurhash=asset.blurhash,
        queued_job=queued_job,
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
    payload: AssetIngestPathRequest,
    request: Request,
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetIngestResponse:
    result = await asset_service.process_new_asset(payload.file_path, current_user.id)
    return _build_ingest_response(request, result.asset, result.queued_job)


@router.post("/upload", response_model=AssetIngestResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    asset_service: AssetService = Depends(get_asset_service),
    current_user: User = Depends(get_current_user),
) -> AssetIngestResponse:
    saved_path = await _save_upload_to_originals(file)
    result = await asset_service.process_new_asset(
        str(saved_path),
        current_user.id,
        uploaded_content_type=file.content_type,
    )
    return _build_ingest_response(request, result.asset, result.queued_job)


@router.post("/scan", response_model=AssetScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def scan_assets(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetScanResponse:
    existing_paths = set(session.exec(select(Asset.master_path).where(active_asset_where())).all())

    scanned_files = 0
    already_ingested = 0
    enqueued_jobs = 0

    try:
        redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to connect to the job queue") from exc

    try:
        for path in MEDIA_ORIGINALS_DIR.rglob("*"):
            if not path.is_file():
                continue
            scanned_files += 1
            relative_path = path.relative_to(MEDIA_ORIGINALS_DIR).as_posix()
            if relative_path in existing_paths:
                already_ingested += 1
                continue
            job = await redis.enqueue_job("ingest_asset_path", relative_path, str(current_user.id))
            if job is not None:
                enqueued_jobs += 1
    finally:
        await redis.aclose()

    return AssetScanResponse(
        scanned_files=scanned_files,
        already_ingested=already_ingested,
        enqueued_jobs=enqueued_jobs,
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
    total = session.exec(select(func.count()).select_from(Asset).where(active_asset_where())).one()
    offset = (page - 1) * page_size

    statement = (
        select(
            Asset,
            tags_subquery.c.tags,
            faces_subquery.c.faces,
        )
        .where(active_asset_where())
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
        .where(Asset.id == asset_id, active_asset_where())
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
        large_preview_url=_detail_image_url(request, asset),
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
