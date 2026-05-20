from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session, col, or_, select

from app.models import Asset, AssetAIProcessing, Job

AI_PROCESSING_STATUS_QUEUED = "queued"
AI_PROCESSING_STATUS_RUNNING = "running"
AI_PROCESSING_STATUS_COMPLETED = "completed"
AI_PROCESSING_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class AIProcessingState:
    row: AssetAIProcessing | None
    last_job: Job | None


class AIProcessingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_state(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int,
        task: str,
    ) -> AIProcessingState:
        row = self.session.exec(
            select(AssetAIProcessing).where(
                AssetAIProcessing.asset_id == asset_id,
                AssetAIProcessing.ai_model_id == ai_model_id,
                AssetAIProcessing.task == task,
            )
        ).first()
        if row is None:
            return AIProcessingState(row=None, last_job=None)
        last_job = self.session.get(Job, row.last_job_id) if row.last_job_id else None
        return AIProcessingState(row=row, last_job=last_job)

    def get_or_create(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int,
        task: str,
    ) -> AssetAIProcessing:
        row = self.session.exec(
            select(AssetAIProcessing).where(
                AssetAIProcessing.asset_id == asset_id,
                AssetAIProcessing.ai_model_id == ai_model_id,
                AssetAIProcessing.task == task,
            )
        ).first()
        if row is not None:
            return row
        row = AssetAIProcessing(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
            status=AI_PROCESSING_STATUS_QUEUED,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row: AssetAIProcessing) -> AssetAIProcessing:
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def asset_has_completed_processing(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int,
        task: str,
    ) -> bool:
        row = self.session.exec(
            select(AssetAIProcessing).where(
                AssetAIProcessing.asset_id == asset_id,
                AssetAIProcessing.ai_model_id == ai_model_id,
                AssetAIProcessing.task == task,
                AssetAIProcessing.status == AI_PROCESSING_STATUS_COMPLETED,
            )
        ).first()
        return row is not None

    def list_asset_ids_needing_clip_processing(
        self,
        *,
        ai_model_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UUID]:
        statement = (
            select(Asset.id)
            .select_from(Asset)
            .outerjoin(
                AssetAIProcessing,
                (
                    (AssetAIProcessing.asset_id == Asset.id)
                    & (AssetAIProcessing.ai_model_id == ai_model_id)
                    & (AssetAIProcessing.task == "clip_embedding")
                ),
            )
            .outerjoin(Job, Job.id == AssetAIProcessing.last_job_id)
            .where(Asset.deleted_at.is_(None))
            .where(
                or_(
                    AssetAIProcessing.id.is_(None),
                    AssetAIProcessing.status == AI_PROCESSING_STATUS_FAILED,
                    (
                        AssetAIProcessing.status.in_(
                            [
                                AI_PROCESSING_STATUS_QUEUED,
                                AI_PROCESSING_STATUS_RUNNING,
                            ]
                        )
                        & (Job.id.is_(None) | (~Job.status.in_(["queued", "running"])))
                    ),
                    (
                        (AssetAIProcessing.status == AI_PROCESSING_STATUS_COMPLETED)
                        & (
                            Asset.search_vector.is_(None)
                            | (Asset.search_model_id != ai_model_id)
                        )
                    ),
                )
            )
            .order_by(Asset.created_at.asc(), Asset.id.asc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    def list_asset_ids_needing_face_processing(
        self,
        *,
        ai_model_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UUID]:
        statement = (
            select(Asset.id)
            .select_from(Asset)
            .outerjoin(
                AssetAIProcessing,
                (
                    (AssetAIProcessing.asset_id == Asset.id)
                    & (AssetAIProcessing.ai_model_id == ai_model_id)
                    & (AssetAIProcessing.task == "face_recognition")
                ),
            )
            .outerjoin(Job, Job.id == AssetAIProcessing.last_job_id)
            .where(
                Asset.deleted_at.is_(None),
                col(Asset.mime_type).like("image/%"),
            )
            .where(
                or_(
                    AssetAIProcessing.id.is_(None),
                    AssetAIProcessing.status == AI_PROCESSING_STATUS_FAILED,
                    (
                        AssetAIProcessing.status.in_(
                            [
                                AI_PROCESSING_STATUS_QUEUED,
                                AI_PROCESSING_STATUS_RUNNING,
                            ]
                        )
                        & (Job.id.is_(None) | (~Job.status.in_(["queued", "running"])))
                    ),
                )
            )
            .order_by(Asset.created_at.asc(), Asset.id.asc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())
