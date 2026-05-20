from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.models import User
from app.services.jobs.schemas import JobDetailRead, JobRead
from app.services.jobs.service import JobService, get_job_service
from app.services.manual_jobs.schemas import (
    ManualJobCatalogRead,
    ManualJobRunRequest,
    ManualJobRunResponse,
)
from app.services.manual_jobs.service import ManualJobService, get_manual_job_service

router = APIRouter()


@router.get("/available", response_model=ManualJobCatalogRead)
def list_available_jobs(
    manual_job_service: ManualJobService = Depends(get_manual_job_service),
    current_user: User = Depends(get_current_user),
) -> ManualJobCatalogRead:
    del current_user
    return manual_job_service.list_available_jobs()


@router.post("/{job_key}/run", response_model=ManualJobRunResponse)
async def run_manual_job(
    job_key: str,
    payload: ManualJobRunRequest | None = None,
    manual_job_service: ManualJobService = Depends(get_manual_job_service),
    current_user: User = Depends(get_current_user),
) -> ManualJobRunResponse:
    job = await manual_job_service.run_manual_job(
        job_key=job_key,
        request=payload,
        requested_by_user_id=current_user.id,
    )
    return ManualJobRunResponse(job=JobRead.model_validate(job, from_attributes=True))


@router.get("", response_model=list[JobRead], include_in_schema=False)
@router.get("/", response_model=list[JobRead])
def list_jobs(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_children: bool = Query(default=False),
    parent_job_id: UUID | None = Query(default=None),
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> list[JobRead]:
    del current_user
    jobs = job_service.list_jobs(
        status=status,
        type=type,
        limit=limit,
        offset=offset,
        include_children=include_children,
        parent_job_id=parent_job_id,
    )
    return [JobRead.model_validate(job, from_attributes=True) for job in jobs]


@router.get("/{job_id}", response_model=JobDetailRead)
def get_job(
    job_id: UUID,
    include_children: bool = Query(default=False),
    manual_job_service: ManualJobService = Depends(get_manual_job_service),
    current_user: User = Depends(get_current_user),
) -> JobDetailRead:
    del current_user
    return manual_job_service.build_job_detail(
        job_id,
        include_children=include_children,
    )
