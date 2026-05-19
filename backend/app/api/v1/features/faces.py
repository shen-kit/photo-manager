from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import get_current_user
from app.models import Face, User
from app.services.faces.query import FaceQueryService, get_face_query_service
from app.services.faces.schemas import AssetFaceRead, FaceBoundingBoxRead
from app.services.faces.tasks import create_backfill_job
from app.services.jobs.queue import (
    enqueue_asset_faces_job,
    enqueue_missing_asset_faces_job,
)
from app.services.jobs.schemas import JobRead
from app.services.jobs.service import JobService, get_job_service

router = APIRouter()


def _crop_url(request: Request, crop_path: str | None) -> str | None:
    if not crop_path:
        return None
    normalized = Path(crop_path).as_posix().lstrip("/")
    return str(request.base_url).rstrip("/") + f"/media/processed/{normalized}"


def _build_face_response(request: Request, face: Face) -> AssetFaceRead:
    bounding_box = None
    if isinstance(face.bounding_box, dict):
        bounding_box = FaceBoundingBoxRead.model_validate(face.bounding_box)
    return AssetFaceRead(
        id=face.id,
        asset_id=face.asset_id,
        person_id=face.person_id,
        bounding_box=bounding_box,
        detection_confidence=face.confidence,
        crop_path=face.crop_path,
        crop_url=_crop_url(request, face.crop_path),
        is_confirmed=face.is_confirmed,
        is_excluded=face.is_excluded,
        created_at=face.created_at,
    )


@router.post(
    "/faces/backfill",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def backfill_asset_faces(
    force: bool = Query(default=False),
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    del current_user
    job_id, _ = create_backfill_job(force=force)
    queued = await enqueue_missing_asset_faces_job(job_id, force=force)
    if not queued:
        job_service.fail_job(job_id, "Failed to enqueue face backfill job")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue face backfill job",
        )
    job = job_service.get_job(job_id)
    return JobRead.model_validate(job, from_attributes=True)


@router.post(
    "/assets/{asset_id}/faces/process",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_asset_faces(
    asset_id: UUID,
    force: bool = Query(default=False),
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    del current_user
    face_query_service.require_active_asset(asset_id)
    job = job_service.create_job(
        "process_asset_faces",
        parameters={"asset_id": str(asset_id), "force": force},
    )
    queued = await enqueue_asset_faces_job(asset_id, force=force, job_id=job.id)
    if not queued:
        job_service.fail_job(job.id, "Failed to enqueue asset face processing job")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue asset face processing job",
        )
    return JobRead.model_validate(job, from_attributes=True)


@router.get(
    "/assets/{asset_id}/faces",
    response_model=list[AssetFaceRead],
)
def list_asset_faces(
    asset_id: UUID,
    request: Request,
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    current_user: User = Depends(get_current_user),
) -> list[AssetFaceRead]:
    del current_user
    faces = face_query_service.list_faces_for_asset(asset_id)
    return [_build_face_response(request, face) for face in faces]
