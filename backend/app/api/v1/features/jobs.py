from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.models import User
from app.services.jobs.schemas import JobRead
from app.services.jobs.service import JobService, get_job_service

router = APIRouter()


@router.get("", response_model=list[JobRead], include_in_schema=False)
@router.get("/", response_model=list[JobRead])
def list_jobs(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> list[JobRead]:
    del current_user
    jobs = job_service.list_jobs(status=status, type=type, limit=limit, offset=offset)
    return [JobRead.model_validate(job, from_attributes=True) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: UUID,
    job_service: JobService = Depends(get_job_service),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    del current_user
    job = job_service.get_job(job_id)
    return JobRead.model_validate(job, from_attributes=True)
