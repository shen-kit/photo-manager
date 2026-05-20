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
from app.services.jobs.context import JobNotification, JobTaskContext
from app.services.notifications.types import NotificationCategory, NotificationLevel

logger = logging.getLogger(__name__)


async def generate_asset_clip_embedding(
    _: dict[str, object],
    asset_id: str,
    force: bool = False,
    job_id: str | None = None,
) -> None:
    job_uuid = UUID(job_id) if job_id else None
    asset_uuid = UUID(asset_id)
    with Session(engine) as session:
        job_context = JobTaskContext(session, job_id=job_uuid)
        tracker = AIProcessingTrackerService(session)
        embedding_service = EmbeddingService(session)
        job_context.mark_running("Generating CLIP embedding")
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
            job_context.fail(
                str(exc),
                notification=JobNotification(
                    level=NotificationLevel.ERROR,
                    category=NotificationCategory.SEARCH,
                    title="Embedding generation failed",
                    message=str(exc),
                    details={"asset_id": asset_id},
                    related_asset_id=asset_uuid,
                ),
            )
            if clip_model is not None:
                tracker.mark_failed(
                    asset_id=asset_uuid,
                    ai_model_id=clip_model.id,
                    task=AI_MODEL_TASK_CLIP_EMBEDDING,
                    job_id=job_uuid,
                    error_message=str(exc),
                )
            return
        tracker.mark_completed(
            asset_id=asset_uuid,
            ai_model_id=result.model_id,
            task=AI_MODEL_TASK_CLIP_EMBEDDING,
            job_id=job_uuid,
            output_count=1,
        )
        job_context.complete(
            "CLIP embedding generated",
            result={
                "asset_id": asset_id,
                "model_id": result.model_id,
                "generated": result.generated,
                "skipped": result.skipped,
            },
        )
