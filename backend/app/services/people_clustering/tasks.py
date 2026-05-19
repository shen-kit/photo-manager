from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel
from app.services.people_clustering.service import (
    CLUSTER_DISTANCE_THRESHOLD,
    CLUSTER_MIN_SIZE,
    CLUSTER_TOP_K,
    PeopleClusteringService,
    PeopleClusteringServiceError,
)

logger = logging.getLogger(__name__)


def create_clustering_job(
    *,
    threshold: float = CLUSTER_DISTANCE_THRESHOLD,
    top_k: int = CLUSTER_TOP_K,
    min_cluster_size: int = CLUSTER_MIN_SIZE,
) -> UUID:
    with Session(engine) as session:
        job = JobService(session).create_job(
            "cluster_faces",
            parameters={
                "threshold": threshold,
                "top_k": top_k,
                "min_cluster_size": min_cluster_size,
            },
        )
        return job.id


async def cluster_faces(
    _: dict[str, object],
    job_id: str,
    threshold: float = CLUSTER_DISTANCE_THRESHOLD,
    top_k: int = CLUSTER_TOP_K,
    min_cluster_size: int = CLUSTER_MIN_SIZE,
) -> dict[str, int]:
    job_uuid = UUID(job_id)
    with Session(engine) as session:
        job_service = JobService(session)
        notification_service = NotificationService(session)
        clustering_service = PeopleClusteringService(session)

        job_service.mark_running(job_uuid, message="Clustering unassigned faces")
        notification_service.create_notification(
            level=NotificationLevel.INFO,
            category=NotificationCategory.FACE,
            title="Face clustering started",
            message="Clustering eligible unassigned faces into people.",
            related_job_id=job_uuid,
            details={
                "threshold": str(threshold),
                "top_k": str(top_k),
                "min_cluster_size": str(min_cluster_size),
            },
        )

        try:
            summary = clustering_service.cluster_unassigned_faces(
                distance_threshold=threshold,
                top_k=top_k,
                min_cluster_size=min_cluster_size,
            )
        except PeopleClusteringServiceError as exc:
            logger.warning("Face clustering failed: %s", exc)
            notification_service.create_notification(
                level=NotificationLevel.ERROR,
                category=NotificationCategory.FACE,
                title="Face clustering failed",
                message=str(exc),
                related_job_id=job_uuid,
            )
            job_service.fail_job(job_uuid, str(exc))
            raise

        result = {
            "candidates_seen": summary.candidates_seen,
            "clusters_created": summary.clusters_created,
            "faces_assigned": summary.faces_assigned,
            "skipped_small_clusters": summary.skipped_small_clusters,
        }
        job_service.complete_job(
            job_uuid,
            result=result,
            message="Face clustering completed",
        )
        notification_service.create_notification(
            level=NotificationLevel.SUCCESS,
            category=NotificationCategory.FACE,
            title="Face clustering completed",
            message="Face clustering completed successfully.",
            related_job_id=job_uuid,
            details={key: str(value) for key, value in result.items()},
        )
        return result
