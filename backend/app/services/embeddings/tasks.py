from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError
from app.services.jobs.queue import enqueue_asset_embedding_job
from app.services.jobs.queue import enqueue_missing_asset_embeddings_job
from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingBackfillStats:
    total: int = 0
    processed: int = 0
    generated: int = 0
    skipped: int = 0
    failed: int = 0

    def to_result(self) -> dict[str, int]:
        return {
            "total": self.total,
            "processed": self.processed,
            "generated": self.generated,
            "skipped": self.skipped,
            "failed": self.failed,
        }


def create_backfill_job(*, force: bool = False) -> tuple[UUID, int]:
    with Session(engine) as session:
        embedding_service = EmbeddingService(session)
        _, total = embedding_service.count_missing_embeddings(force=force)
        job = JobService(session).create_job(
            "generate_missing_asset_clip_embeddings",
            parameters={"force": force},
            progress_total=total,
        )
        return job.id, total


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
        if job_uuid is not None:
            job_service.mark_running(job_uuid, message="Generating CLIP embedding")
        try:
            result = EmbeddingService(session).generate_for_asset(
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
            return
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


async def generate_missing_asset_clip_embeddings(
    _: dict[str, object],
    job_id: str,
    force: bool = False,
) -> dict[str, int]:
    job_uuid = UUID(job_id)
    stats = EmbeddingBackfillStats()
    with Session(engine) as session:
        job_service = JobService(session)
        notification_service = NotificationService(session)
        embedding_service = EmbeddingService(session)
        _, asset_ids = embedding_service.list_missing_asset_ids(force=force)
        stats = EmbeddingBackfillStats(total=len(asset_ids))
        job_service.mark_running(job_uuid, message="Generating missing CLIP embeddings")
        job_service.update_progress(job_uuid, total=stats.total)
        notification_service.create_notification(
            level=NotificationLevel.INFO,
            category=NotificationCategory.SEARCH,
            title="Embedding backfill started",
            message="Generating CLIP embeddings for assets missing them.",
            related_job_id=job_uuid,
            details={"total": str(stats.total), "force": str(force)},
        )

        for index, asset_uuid in enumerate(asset_ids, start=1):
            try:
                result = embedding_service.generate_for_asset(asset_uuid, force=force)
            except EmbeddingServiceError as exc:
                logger.warning(
                    "Embedding backfill failed for asset %s: %s", asset_uuid, exc
                )
                stats = EmbeddingBackfillStats(
                    total=stats.total,
                    processed=index,
                    generated=stats.generated,
                    skipped=stats.skipped,
                    failed=stats.failed + 1,
                )
                notification_service.create_notification(
                    level=NotificationLevel.ERROR,
                    category=NotificationCategory.SEARCH,
                    title="Embedding generation failed",
                    message=str(exc),
                    related_job_id=job_uuid,
                    related_asset_id=asset_uuid,
                )
            else:
                stats = EmbeddingBackfillStats(
                    total=stats.total,
                    processed=index,
                    generated=stats.generated + int(result.generated),
                    skipped=stats.skipped + int(result.skipped),
                    failed=stats.failed,
                )
            job_service.update_progress(
                job_uuid,
                current=stats.processed,
                total=stats.total,
                message=(
                    f"Processed {stats.processed}/{stats.total} assets, "
                    f"generated {stats.generated}, skipped {stats.skipped}, failed {stats.failed}"
                ),
            )

        job_service.complete_job(
            job_uuid,
            result=stats.to_result(),
            message="CLIP embedding backfill completed",
        )
        notification_service.create_notification(
            level=NotificationLevel.SUCCESS,
            category=NotificationCategory.SEARCH,
            title="Embedding backfill completed",
            message="CLIP embedding generation completed.",
            related_job_id=job_uuid,
            details={key: str(value) for key, value in stats.to_result().items()},
        )
        return stats.to_result()
