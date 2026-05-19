from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import SQLModel

from app.core.auth import get_current_user
from app.models import Asset, User
from app.services.jobs.queue import enqueue_face_clustering_job
from app.services.jobs.schemas import JobRead
from app.services.jobs.service import JobService, get_job_service
from app.services.people.schemas import (
    FaceSummary,
    PersonAssetItem,
    PersonAssetListResponse,
    PersonMergeResponse,
    PersonRead,
    PersonSummary,
    PersonThumbnailUpdateRequest,
    PersonUpdateRequest,
    TagSummary,
)
from app.services.people.service import PeopleService, get_people_service
from app.services.people_clustering.service import (
    CLUSTER_DISTANCE_THRESHOLD,
    CLUSTER_MIN_SIZE,
    CLUSTER_TOP_K,
)
from app.services.people_clustering.tasks import create_clustering_job

router = APIRouter()


class PeopleClusteringRequest(SQLModel):
    threshold: float = CLUSTER_DISTANCE_THRESHOLD
    top_k: int = CLUSTER_TOP_K
    min_cluster_size: int = CLUSTER_MIN_SIZE


def _person_thumbnail_url(request: Request, thumbnail_path: str | None) -> str | None:
    if not thumbnail_path:
        return None
    normalized = Path(thumbnail_path).as_posix().lstrip("/")
    return str(request.base_url).rstrip("/") + f"/media/processed/{normalized}"


def _thumbnail_url(request: Request, asset_id: UUID, variant: str = "small") -> str:
    return (
        str(request.base_url).rstrip("/")
        + f"/media/processed/assets/{asset_id}/{variant}.webp"
    )


def _build_tag_models(rows: list[dict[str, object]] | None) -> list[TagSummary]:
    return [TagSummary.model_validate(row) for row in (rows or [])]


def _build_face_models(rows: list[dict[str, object]] | None) -> list[FaceSummary]:
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


def _build_person_read(request: Request, row) -> PersonRead:
    return PersonRead(
        id=row.person.id,
        name=row.person.name,
        thumbnail_face_id=row.person.thumbnail_face_id,
        thumbnail_path=row.person.thumbnail_path,
        thumbnail_url=_person_thumbnail_url(request, row.person.thumbnail_path),
        thumbnail_manually_set=row.person.thumbnail_manually_set,
        face_count=row.face_count,
        asset_count=row.asset_count,
        is_hidden=row.person.is_hidden,
    )


def _build_asset_item(
    request: Request,
    asset: Asset,
    tags: list[dict[str, object]] | None,
    faces: list[dict[str, object]] | None,
) -> PersonAssetItem:
    return PersonAssetItem(
        id=asset.id,
        captured_at=asset.captured_at,
        description=asset.description,
        is_favorite=asset.is_favorite,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        small_thumbnail_url=_thumbnail_url(request, asset.id),
        blurhash=asset.blurhash,
        tags=_build_tag_models(tags),
        faces=_build_face_models(faces),
    )


@router.post(
    "/people/cluster",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cluster_people(
    payload: PeopleClusteringRequest,
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    del current_user
    if not 0.2 <= payload.threshold <= 0.8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="threshold must be between 0.2 and 0.8",
        )
    if not 5 <= payload.top_k <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="top_k must be between 5 and 100",
        )
    if not 2 <= payload.min_cluster_size <= 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_cluster_size must be between 2 and 20",
        )

    job_id = create_clustering_job(
        threshold=payload.threshold,
        top_k=payload.top_k,
        min_cluster_size=payload.min_cluster_size,
    )
    queued = await enqueue_face_clustering_job(
        job_id,
        threshold=payload.threshold,
        top_k=payload.top_k,
        min_cluster_size=payload.min_cluster_size,
    )
    if not queued:
        job_service.fail_job(job_id, "Failed to enqueue face clustering job")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue face clustering job",
        )
    job = job_service.get_job(job_id)
    return JobRead.model_validate(job, from_attributes=True)


@router.get("/people", response_model=list[PersonRead], include_in_schema=False)
@router.get("/people/", response_model=list[PersonRead])
def list_people(
    request: Request,
    include_hidden: bool = Query(default=False),
    search: str | None = Query(default=None),
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> list[PersonRead]:
    del current_user
    rows = people_service.list_people(include_hidden=include_hidden, search=search)
    return [_build_person_read(request, row) for row in rows]


@router.get("/people/{person_id}", response_model=PersonRead)
def get_person(
    person_id: UUID,
    request: Request,
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    del current_user
    return _build_person_read(request, people_service.get_person_detail(person_id))


@router.patch("/people/{person_id}", response_model=PersonRead)
def update_person(
    person_id: UUID,
    payload: PersonUpdateRequest,
    request: Request,
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    del current_user
    updates = payload.model_dump(exclude_unset=True)
    updated = people_service.update_person(person_id, **updates)
    return _build_person_read(request, updated)


@router.patch("/people/{person_id}/thumbnail", response_model=PersonRead)
def update_person_thumbnail(
    person_id: UUID,
    payload: PersonThumbnailUpdateRequest,
    request: Request,
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    del current_user
    updated = people_service.set_thumbnail(
        person_id=person_id,
        asset_id=payload.asset_id,
    )
    return _build_person_read(request, updated)


@router.get("/people/{person_id}/assets", response_model=PersonAssetListResponse)
def list_person_assets(
    person_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> PersonAssetListResponse:
    del current_user
    total, rows = people_service.list_assets_for_person(
        person_id=person_id,
        page=page,
        page_size=page_size,
    )
    return PersonAssetListResponse(
        items=[_build_asset_item(request, asset, tags, faces) for asset, tags, faces in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/people/{source_person_id}/merge-into/{target_person_id}",
    response_model=PersonMergeResponse,
)
def merge_people(
    source_person_id: UUID,
    target_person_id: UUID,
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> PersonMergeResponse:
    del current_user
    summary = people_service.merge_people(
        source_person_id=source_person_id,
        target_person_id=target_person_id,
    )
    return PersonMergeResponse(
        faces_moved=summary.faces_moved,
        source_deleted=summary.source_deleted,
        target_person_id=summary.target_person_id,
    )
