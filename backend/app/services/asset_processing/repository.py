from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session, col, or_, select

from app.models import Asset, AssetProcessing, Job

PROCESSING_STATUS_QUEUED = "queued"
PROCESSING_STATUS_RUNNING = "running"
PROCESSING_STATUS_COMPLETED = "completed"
PROCESSING_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class AssetProcessingState:
    row: AssetProcessing | None
    last_job: Job | None


class AssetProcessingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_state(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
    ) -> AssetProcessingState:
        row = self.session.exec(
            select(AssetProcessing).where(
                *self._filters(
                    asset_id=asset_id,
                    ai_model_id=ai_model_id,
                    task=task,
                )
            )
        ).first()
        if row is None:
            return AssetProcessingState(row=None, last_job=None)
        last_job = self.session.get(Job, row.last_job_id) if row.last_job_id else None
        return AssetProcessingState(row=row, last_job=last_job)

    def get_or_create(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
    ) -> AssetProcessing:
        row = self.session.exec(
            select(AssetProcessing).where(
                *self._filters(
                    asset_id=asset_id,
                    ai_model_id=ai_model_id,
                    task=task,
                )
            )
        ).first()
        if row is not None:
            return row
        row = AssetProcessing(
            asset_id=asset_id,
            ai_model_id=ai_model_id,
            task=task,
            status=PROCESSING_STATUS_QUEUED,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, row: AssetProcessing) -> AssetProcessing:
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def asset_has_completed_processing(
        self,
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
    ) -> bool:
        row = self.session.exec(
            select(AssetProcessing).where(
                *self._filters(
                    asset_id=asset_id,
                    ai_model_id=ai_model_id,
                    task=task,
                ),
                AssetProcessing.status == PROCESSING_STATUS_COMPLETED,
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
                AssetProcessing,
                (
                    (AssetProcessing.asset_id == Asset.id)
                    & (AssetProcessing.ai_model_id == ai_model_id)
                    & (AssetProcessing.task == "clip_embedding")
                ),
            )
            .outerjoin(Job, Job.id == AssetProcessing.last_job_id)
            .where(Asset.deleted_at.is_(None))
            .where(
                or_(
                    AssetProcessing.id.is_(None),
                    AssetProcessing.status == PROCESSING_STATUS_FAILED,
                    (
                        AssetProcessing.status.in_(
                            [PROCESSING_STATUS_QUEUED, PROCESSING_STATUS_RUNNING]
                        )
                        & (Job.id.is_(None) | (~Job.status.in_(["queued", "running"])))
                    ),
                    (
                        (AssetProcessing.status == PROCESSING_STATUS_COMPLETED)
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
                AssetProcessing,
                (
                    (AssetProcessing.asset_id == Asset.id)
                    & (AssetProcessing.ai_model_id == ai_model_id)
                    & (AssetProcessing.task == "face_recognition")
                ),
            )
            .outerjoin(Job, Job.id == AssetProcessing.last_job_id)
            .where(
                Asset.deleted_at.is_(None),
                col(Asset.mime_type).like("image/%"),
            )
            .where(
                or_(
                    AssetProcessing.id.is_(None),
                    AssetProcessing.status == PROCESSING_STATUS_FAILED,
                    (
                        AssetProcessing.status.in_(
                            [PROCESSING_STATUS_QUEUED, PROCESSING_STATUS_RUNNING]
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

    @staticmethod
    def _filters(
        *,
        asset_id: UUID,
        ai_model_id: int | None,
        task: str,
    ) -> list[object]:
        filters: list[object] = [
            AssetProcessing.asset_id == asset_id,
            AssetProcessing.task == task,
        ]
        if ai_model_id is None:
            filters.append(AssetProcessing.ai_model_id.is_(None))
        else:
            filters.append(AssetProcessing.ai_model_id == ai_model_id)
        return filters
