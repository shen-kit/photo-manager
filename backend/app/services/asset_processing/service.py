from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.models import utc_now
from app.services.asset_processing.repository import (
    PROCESSING_STATUS_COMPLETED,
    PROCESSING_STATUS_FAILED,
    PROCESSING_STATUS_QUEUED,
    PROCESSING_STATUS_RUNNING,
    AssetProcessingRepository,
)


class AssetProcessingTrackerService:
    def __init__(
        self,
        session: Session,
        *,
        repository: AssetProcessingRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or AssetProcessingRepository(session)

    def mark_queued(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
        job_id: UUID | None,
    ) -> None:
        row = self.repository.get_or_create(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
        )
        row.status = PROCESSING_STATUS_QUEUED
        row.error_message = None
        row.last_job_id = job_id
        row.started_at = None
        row.processed_at = None
        self.repository.save(row)

    def mark_running(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
        job_id: UUID | None,
    ) -> None:
        row = self.repository.get_or_create(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
        )
        row.status = PROCESSING_STATUS_RUNNING
        row.error_message = None
        row.last_job_id = job_id
        row.started_at = utc_now()
        self.repository.save(row)

    def mark_completed(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
        job_id: UUID | None,
        output_count: int,
    ) -> None:
        row = self.repository.get_or_create(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
        )
        row.status = PROCESSING_STATUS_COMPLETED
        row.error_message = None
        row.last_job_id = job_id
        if row.started_at is None:
            row.started_at = utc_now()
        row.processed_at = utc_now()
        row.output_count = output_count
        self.repository.save(row)

    def mark_failed(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
        job_id: UUID | None,
        error_message: str,
    ) -> None:
        row = self.repository.get_or_create(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
        )
        row.status = PROCESSING_STATUS_FAILED
        row.error_message = error_message
        row.last_job_id = job_id
        if row.started_at is None:
            row.started_at = utc_now()
        row.processed_at = None
        self.repository.save(row)
