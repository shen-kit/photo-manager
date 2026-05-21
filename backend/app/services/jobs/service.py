from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.database import get_session
from app.models import Job, utc_now

ACTIVE_JOB_STATUSES = ("queued", "running")
TERMINAL_JOB_STATUSES = ("completed", "failed", "cancelled")


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        type: str,
        parameters: dict[str, Any] | None = None,
        progress_total: int | None = None,
        *,
        job_key: str | None = None,
        parent_job_id: UUID | None = None,
        related_asset_id: UUID | None = None,
        is_visible: bool = True,
    ) -> Job:
        job = Job(
            type=type,
            job_key=job_key,
            status="queued",
            parameters=parameters,
            progress_total=progress_total,
            progress_current=0,
            parent_job_id=parent_job_id,
            related_asset_id=related_asset_id,
            is_visible=is_visible,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_job(self, job_id: UUID) -> Job:
        job = self.session.get(Job, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )
        return job

    def get_job_or_none(self, job_id: UUID) -> Job | None:
        return self.session.get(Job, job_id)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_children: bool = False,
        parent_job_id: UUID | None = None,
    ) -> list[Job]:
        statement = (
            select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
        )
        if not include_children and parent_job_id is None:
            statement = statement.where(Job.is_visible.is_(True))
        if status is not None:
            statement = statement.where(Job.status == status)
        if type is not None:
            statement = statement.where(Job.type == type)
        if parent_job_id is not None:
            statement = statement.where(Job.parent_job_id == parent_job_id)
        return list(self.session.exec(statement).all())

    def list_child_jobs(self, *, parent_job_id: UUID, limit: int = 500) -> list[Job]:
        statement = (
            select(Job)
            .where(Job.parent_job_id == parent_job_id)
            .order_by(Job.created_at.asc(), Job.id.asc())
            .limit(limit)
        )
        return list(self.session.exec(statement).all())

    def get_child_job_for_asset(
        self,
        *,
        parent_job_id: UUID,
        related_asset_id: UUID,
    ) -> Job | None:
        statement = select(Job).where(
            Job.parent_job_id == parent_job_id,
            Job.related_asset_id == related_asset_id,
        )
        return self.session.exec(statement).first()

    def get_child_counts(self, *, parent_job_id: UUID) -> dict[str, int]:
        rows = self.session.exec(
            select(Job.status, func.count())
            .where(Job.parent_job_id == parent_job_id)
            .group_by(Job.status)
        ).all()
        counts = {
            "total": 0,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        for job_status, count in rows:
            counts["total"] += int(count)
            if job_status in counts:
                counts[job_status] = int(count)
        return counts

    def find_active_job_by_key(self, *, job_key: str) -> Job | None:
        statement = (
            select(Job)
            .where(
                Job.job_key == job_key,
                Job.parent_job_id.is_(None),
                Job.is_visible.is_(True),
                Job.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(Job.created_at.desc())
        )
        return self.session.exec(statement).first()

    def find_active_job_for_asset(
        self,
        *,
        job_key: str,
        related_asset_id: UUID,
    ) -> Job | None:
        statement = (
            select(Job)
            .where(
                Job.job_key == job_key,
                Job.related_asset_id == related_asset_id,
                Job.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(Job.created_at.desc())
        )
        return self.session.exec(statement).first()

    def get_latest_visible_job_by_key(self, *, job_key: str) -> Job | None:
        statement = (
            select(Job)
            .where(
                Job.job_key == job_key,
                Job.parent_job_id.is_(None),
                Job.is_visible.is_(True),
            )
            .order_by(Job.created_at.desc())
        )
        return self.session.exec(statement).first()

    def count_terminal_children(self, *, parent_job_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Job)
            .where(
                Job.parent_job_id == parent_job_id,
                Job.status.in_(TERMINAL_JOB_STATUSES),
            )
        )
        return int(self.session.exec(statement).one())

    def mark_running(self, job_id: UUID, message: str | None = None) -> Job:
        job = self.get_job(job_id)
        started_at = job.started_at or utc_now()
        return self._update_job(
            job_id,
            status="running",
            progress_message=message,
            started_at=started_at,
            finished_at=None,
            error_message=None,
        )

    def update_progress(
        self,
        job_id: UUID,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> Job:
        values: dict[str, Any] = {}
        if current is not None:
            values["progress_current"] = current
        if total is not None:
            values["progress_total"] = total
        if message is not None:
            values["progress_message"] = message
        return self._update_job(job_id, **values)

    def complete_job(
        self,
        job_id: UUID,
        *,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> Job:
        job = self.get_job(job_id)
        progress_current = (
            job.progress_total
            if job.progress_total is not None and job.parent_job_id is None
            else job.progress_current
        )
        return self._update_job(
            job_id,
            status="completed",
            progress_current=progress_current,
            progress_message=message,
            result=result,
            error_message=None,
            finished_at=utc_now(),
        )

    def fail_job(
        self,
        job_id: UUID,
        error_message: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> Job:
        return self._update_job(
            job_id,
            status="failed",
            error_message=error_message,
            result=result,
            finished_at=utc_now(),
        )

    def cancel_job(self, job_id: UUID, message: str | None = None) -> Job:
        return self._update_job(
            job_id,
            status="cancelled",
            progress_message=message,
            finished_at=utc_now(),
        )

    def _update_job(self, job_id: UUID, **values: Any) -> Job:
        job = self.get_job(job_id)
        for field_name, value in values.items():
            if value is None and field_name not in {
                "started_at",
                "finished_at",
                "result",
                "error_message",
            }:
                continue
            setattr(job, field_name, value)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job


def get_job_service(session: Session = Depends(get_session)) -> JobService:
    return JobService(session=session)
