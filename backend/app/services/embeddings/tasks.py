from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AIModelConfigurationError,
)
from app.services.ai_processing.service import AIProcessingTrackerService
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError
from app.services.jobs.queue import enqueue_asset_embedding_job
from app.services.jobs.service import JobService
from app.services.manual_jobs.service import ManualJobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel

logger = logging.getLogger(__name__)


def _mark_job_failed(
    *,
    session: Session,
    job_id: UUID | None,
    message: str,
    asset_id: UUID | None = None,
    details: dict[str, str] | None = None,
) -> None:
    NotificationService(session).create_notification(
        level=NotificationLevel.ERROR,
        category=NotificationCategory.SEARCH,
        title="Embedding generation failed",
        message=message,
        details=details,
        related_job_id=job_id,
        related_asset_id=asset_id,
    )
    if job_id is not None:
        JobService(session).fail_job(job_id, message)


async def generate_asset_clip_embedding(
    _: dict[str, object],
    asset_id: str,
    force: bool = False,
    job_id: str | None = None,
) -> None:
    job_uuid = UUID(job_id) if job_id else None
    asset_uuid = UUID(asset_id)
    with Session(engine) as session:
        job_service = JobService(session)
        manual_job_service = ManualJobService(session)
        tracker = AIProcessingTrackerService(session)
        embedding_service = EmbeddingService(session)
        if job_uuid is not None:
            job_service.mark_running(job_uuid, message="Generating CLIP embedding")
        try:
            clip_model = (
                embedding_service.ai_model_repository.get_default_model_for_task(
                    AI_MODEL_TASK_CLIP_EMBEDDING
                )
            )
        except AIModelConfigurationError:
            clip_model = None
        if clip_model is not None:
            tracker.mark_running(
                asset_id=asset_uuid,
                ai_model_id=clip_model.id,
                task=AI_MODEL_TASK_CLIP_EMBEDDING,
                job_id=job_uuid,
            )
        try:
            result = embedding_service.generate_for_asset(
                asset_uuid,
                force=force,
            )
        except EmbeddingServiceError as exc:
            logger.warning(
                "Embedding generation failed for asset %s: %s", asset_uuid, exc
            )
            _mark_job_failed(
                session=session,
                job_id=job_uuid,
                message=str(exc),
                asset_id=asset_uuid,
                details={"asset_id": asset_id},
            )
            if clip_model is not None:
                tracker.mark_failed(
                    asset_id=asset_uuid,
                    ai_model_id=clip_model.id,
                    task=AI_MODEL_TASK_CLIP_EMBEDDING,
                    job_id=job_uuid,
                    error_message=str(exc),
                )
            if job_uuid is not None:
                manual_job_service.on_child_job_terminal(job_uuid)
            return
        tracker.mark_completed(
            asset_id=asset_uuid,
            ai_model_id=result.model_id,
            task=AI_MODEL_TASK_CLIP_EMBEDDING,
            job_id=job_uuid,
            output_count=1,
        )
        if job_uuid is not None:
            job_service.complete_job(
                job_uuid,
                result={
                    "asset_id": asset_id,
                    "model_id": result.model_id,
                    "generated": result.generated,
                    "skipped": result.skipped,
                },
                message="CLIP embedding generated",
            )
            manual_job_service.on_child_job_terminal(job_uuid)
