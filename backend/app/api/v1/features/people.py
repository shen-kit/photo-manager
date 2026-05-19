from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import SQLModel

from app.core.auth import get_current_user
from app.models import User
from app.services.jobs.queue import enqueue_face_clustering_job
from app.services.jobs.schemas import JobRead
from app.services.jobs.service import JobService, get_job_service
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
