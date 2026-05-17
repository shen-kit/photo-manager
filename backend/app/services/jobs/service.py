from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models import Job, utc_now


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        type: str,
        parameters: dict[str, Any] | None = None,
        progress_total: int | None = None,
    ) -> Job:
        job = Job(
            type=type,
            status="queued",
            parameters=parameters,
            progress_total=progress_total,
            progress_current=0,
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

    def list_jobs(
        self,
        *,
        status: str | None = None,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        statement = (
            select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
        )
        if status is not None:
            statement = statement.where(Job.status == status)
        if type is not None:
            statement = statement.where(Job.type == type)
        return list(self.session.exec(statement).all())

    def mark_running(self, job_id: UUID, message: str | None = None) -> Job:
        return self._update_job(
            job_id,
            status="running",
            progress_message=message,
            started_at=utc_now(),
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
            if job.progress_total is not None
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
