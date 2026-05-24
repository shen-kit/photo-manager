from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import DiagnosticRun, DiagnosticRunItem, Job


@dataclass(frozen=True)
class DiagnosticRunWithJobs:
    run: DiagnosticRun
    related_job: Job | None
    latest_repair_job: Job | None


class SystemIntegrityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        *,
        diagnostic_key: str,
        status: str = "queued",
        repair_job_key: str | None = None,
        requested_by_user_id: UUID | None = None,
        related_job_id: UUID | None = None,
    ) -> DiagnosticRun:
        run = DiagnosticRun(
            diagnostic_key=diagnostic_key,
            status=status,
            repair_job_key=repair_job_key,
            requested_by_user_id=requested_by_user_id,
            related_job_id=related_job_id,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def save_run(self, run: DiagnosticRun) -> DiagnosticRun:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, run_id: UUID) -> DiagnosticRun:
        run = self.session.get(DiagnosticRun, run_id)
        if run is None:
            raise KeyError(f"Diagnostic run {run_id} not found")
        return run

    def get_run_with_jobs(self, run_id: UUID) -> DiagnosticRunWithJobs:
        run = self.get_run(run_id)
        return DiagnosticRunWithJobs(
            run=run,
            related_job=self.session.get(Job, run.related_job_id)
            if run.related_job_id
            else None,
            latest_repair_job=self.session.get(Job, run.latest_repair_job_id)
            if run.latest_repair_job_id
            else None,
        )

    def list_runs(
        self,
        *,
        diagnostic_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiagnosticRun]:
        statement = select(DiagnosticRun).order_by(
            DiagnosticRun.created_at.desc(),
            DiagnosticRun.id.desc(),
        )
        if diagnostic_key is not None:
            statement = statement.where(DiagnosticRun.diagnostic_key == diagnostic_key)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.exec(statement).all())

    def get_latest_run(self, *, diagnostic_key: str) -> DiagnosticRun | None:
        statement = (
            select(DiagnosticRun)
            .where(DiagnosticRun.diagnostic_key == diagnostic_key)
            .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
        )
        return self.session.exec(statement).first()

    def get_active_run(self, *, diagnostic_key: str) -> DiagnosticRun | None:
        statement = (
            select(DiagnosticRun)
            .where(
                DiagnosticRun.diagnostic_key == diagnostic_key,
                DiagnosticRun.status.in_(("queued", "running")),
            )
            .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
        )
        return self.session.exec(statement).first()

    def add_run_items(
        self,
        *,
        diagnostic_run_id: UUID,
        items: list[dict[str, Any]],
    ) -> None:
        rows = [
            DiagnosticRunItem(diagnostic_run_id=diagnostic_run_id, **item)
            for item in items
        ]
        if not rows:
            return
        self.session.add_all(rows)
        self.session.commit()

    def list_run_items(
        self,
        *,
        diagnostic_run_id: UUID,
        limit: int | None = 100,
        offset: int = 0,
    ) -> list[DiagnosticRunItem]:
        statement = (
            select(DiagnosticRunItem)
            .where(DiagnosticRunItem.diagnostic_run_id == diagnostic_run_id)
            .order_by(DiagnosticRunItem.id.asc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    def count_run_items(self, *, diagnostic_run_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(DiagnosticRunItem)
            .where(DiagnosticRunItem.diagnostic_run_id == diagnostic_run_id)
        )
        return int(self.session.exec(statement).one())

    def list_runs_for_retention(self, *, diagnostic_key: str) -> list[DiagnosticRun]:
        statement = (
            select(DiagnosticRun)
            .where(DiagnosticRun.diagnostic_key == diagnostic_key)
            .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
        )
        return list(self.session.exec(statement).all())

    def delete_runs(self, runs: list[DiagnosticRun]) -> None:
        for run in runs:
            self.session.delete(run)
        self.session.commit()
