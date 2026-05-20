from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.services.ai_models.repository import (
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
)
from app.services.ai_processing.service import AIProcessingTrackerService
from app.services.face_assignment.service import (
    FaceAssignmentService,
    FaceAssignmentServiceError,
)
from app.services.faces.service import FaceProcessingService, FaceProcessingServiceError
from app.services.jobs.context import JobNotification, JobTaskContext
from app.services.notifications.types import NotificationCategory, NotificationLevel

logger = logging.getLogger(__name__)


async def process_asset_faces(
    _: dict[str, object],
    asset_id: str,
    force: bool = False,
    auto_match: bool = True,
    job_id: str | None = None,
) -> None:
    job_uuid = UUID(job_id) if job_id else None
    asset_uuid = UUID(asset_id)
    with Session(engine) as session:
        job_context = JobTaskContext(session, job_id=job_uuid)
        tracker = AIProcessingTrackerService(session)
        face_service = FaceProcessingService(session)
        job_context.mark_running("Processing asset faces")
        try:
            face_model = face_service.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError:
            face_model = None
        if face_model is not None:
            tracker.mark_running(
                asset_id=asset_uuid,
                ai_model_id=face_model.id,
                task=AI_MODEL_TASK_FACE_RECOGNITION,
                job_id=job_uuid,
            )
        try:
            result = face_service.process_asset_faces(
                asset_uuid,
                force=force,
            )
            assignment_result = None
            if auto_match and result.processed:
                assignment_result = FaceAssignmentService(
                    session
                ).assign_faces_for_asset(asset_uuid)
        except (FaceProcessingServiceError, FaceAssignmentServiceError) as exc:
            logger.warning("Face processing failed for asset %s: %s", asset_uuid, exc)
            job_context.fail(
                str(exc),
                notification=JobNotification(
                    level=NotificationLevel.ERROR,
                    category=NotificationCategory.FACE,
                    title="Face processing failed",
                    message=str(exc),
                    details={"asset_id": asset_id},
                    related_asset_id=asset_uuid,
                ),
            )
            if face_model is not None:
                tracker.mark_failed(
                    asset_id=asset_uuid,
                    ai_model_id=face_model.id,
                    task=AI_MODEL_TASK_FACE_RECOGNITION,
                    job_id=job_uuid,
                    error_message=str(exc),
                )
            return
        tracker.mark_completed(
            asset_id=asset_uuid,
            ai_model_id=result.model_id,
            task=AI_MODEL_TASK_FACE_RECOGNITION,
            job_id=job_uuid,
            output_count=result.detected_faces,
        )
        job_context.complete(
            "Asset faces processed",
            result={
                "asset_id": asset_id,
                "model_id": result.model_id,
                "processed": result.processed,
                "skipped": result.skipped,
                "auto_match": auto_match,
                "faces_created": result.faces_created,
                "detected_faces": result.detected_faces,
                "deleted_unconfirmed_faces": result.deleted_unconfirmed_faces,
                "faces_seen_for_matching": (
                    assignment_result.faces_seen
                    if assignment_result is not None
                    else 0
                ),
                "faces_matched": (
                    assignment_result.faces_matched
                    if assignment_result is not None
                    else 0
                ),
                "faces_unmatched": (
                    assignment_result.faces_unmatched
                    if assignment_result is not None
                    else 0
                ),
            },
        )
