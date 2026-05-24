from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.models import DiagnosticRun, utc_now
from app.services.jobs.schemas import JobRead
from app.services.system_integrity.definitions import (
    DIAGNOSTIC_DEFINITION_BY_KEY,
    DIAGNOSTIC_DEFINITIONS,
)
from app.services.system_integrity.repository import SystemIntegrityRepository
from app.services.system_integrity.schemas import (
    DiagnosticDefinitionListRead,
    DiagnosticDefinitionRead,
    DiagnosticRunDetailRead,
    DiagnosticRunItemPageRead,
    DiagnosticRunItemRead,
    DiagnosticRunListRead,
    DiagnosticRunRead,
)


class SystemIntegrityService:
    def __init__(
        self,
        session: Session,
        *,
        repository: SystemIntegrityRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or SystemIntegrityRepository(session)

    def list_definitions(self) -> DiagnosticDefinitionListRead:
        items: list[DiagnosticDefinitionRead] = []
        for definition in DIAGNOSTIC_DEFINITIONS:
            latest_run = self.repository.get_latest_run(diagnostic_key=definition.key)
            active_run = self.repository.get_active_run(diagnostic_key=definition.key)
            items.append(
                DiagnosticDefinitionRead(
                    key=definition.key,
                    title=definition.title,
                    description=definition.description,
                    supports_repair=definition.supports_repair,
                    repair_job_key=definition.repair_job_key,
                    latest_run_id=latest_run.id if latest_run else None,
                    latest_status=latest_run.status if latest_run else None,
                    latest_health_state=latest_run.health_state if latest_run else None,
                    latest_checked_at=latest_run.checked_at if latest_run else None,
                    active_run_id=active_run.id if active_run else None,
                )
            )
        return DiagnosticDefinitionListRead(items=items)

    def create_run(
        self,
        *,
        diagnostic_key: str,
        requested_by_user_id: UUID | None = None,
    ) -> DiagnosticRun:
        definition = DIAGNOSTIC_DEFINITION_BY_KEY.get(diagnostic_key)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic not found",
            )
        active_run = self.repository.get_active_run(diagnostic_key=diagnostic_key)
        if active_run is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Diagnostic already active",
                    "diagnostic_key": diagnostic_key,
                    "active_run_id": str(active_run.id),
                },
            )
        return self.repository.create_run(
            diagnostic_key=diagnostic_key,
            repair_job_key=definition.repair_job_key,
            requested_by_user_id=requested_by_user_id,
        )

    def attach_related_job(self, *, run_id: UUID, related_job_id: UUID) -> DiagnosticRun:
        run = self.repository.get_run(run_id)
        run.related_job_id = related_job_id
        return self.repository.save_run(run)

    def attach_latest_repair_job(
        self,
        *,
        run_id: UUID,
        latest_repair_job_id: UUID,
    ) -> DiagnosticRun:
        run = self.repository.get_run(run_id)
        run.latest_repair_job_id = latest_repair_job_id
        return self.repository.save_run(run)

    def get_run_read(self, run: DiagnosticRun) -> DiagnosticRunRead:
        return DiagnosticRunRead.model_validate(run, from_attributes=True)

    def list_runs(
        self,
        *,
        diagnostic_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> DiagnosticRunListRead:
        return DiagnosticRunListRead(
            items=[
                DiagnosticRunRead.model_validate(run, from_attributes=True)
                for run in self.repository.list_runs(
                    diagnostic_key=diagnostic_key,
                    limit=limit,
                    offset=offset,
                )
            ]
        )

    def get_latest_run(self, *, diagnostic_key: str) -> DiagnosticRunRead:
        if diagnostic_key not in DIAGNOSTIC_DEFINITION_BY_KEY:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic not found",
            )
        run = self.repository.get_latest_run(diagnostic_key=diagnostic_key)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic run not found",
            )
        return DiagnosticRunRead.model_validate(run, from_attributes=True)

    def get_run_model(self, run_id: UUID) -> DiagnosticRun:
        try:
            return self.repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic run not found",
            ) from exc

    def get_run_detail(self, run_id: UUID) -> DiagnosticRunDetailRead:
        try:
            payload = self.repository.get_run_with_jobs(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic run not found",
            ) from exc
        return DiagnosticRunDetailRead(
            **DiagnosticRunRead.model_validate(
                payload.run, from_attributes=True
            ).model_dump(),
            related_job=JobRead.model_validate(payload.related_job, from_attributes=True)
            if payload.related_job is not None
            else None,
            latest_repair_job=JobRead.model_validate(
                payload.latest_repair_job, from_attributes=True
            )
            if payload.latest_repair_job is not None
            else None,
        )

    def list_run_items(
        self,
        *,
        run_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> DiagnosticRunItemPageRead:
        try:
            self.repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic run not found",
            ) from exc
        items = self.repository.list_run_items(
            diagnostic_run_id=run_id,
            limit=limit,
            offset=offset,
        )
        total = self.repository.count_run_items(diagnostic_run_id=run_id)
        return DiagnosticRunItemPageRead(
            items=[
                DiagnosticRunItemRead.model_validate(item, from_attributes=True)
                for item in items
            ],
            limit=limit,
            offset=offset,
            total=total,
        )

    def mark_run_started(self, run_id: UUID) -> DiagnosticRun:
        run = self.repository.get_run(run_id)
        run.status = "running"
        run.started_at = run.started_at or utc_now()
        run.finished_at = None
        run.error_message = None
        return self.repository.save_run(run)

    def mark_run_completed(
        self,
        run_id: UUID,
        *,
        health_state: str,
        summary_json: dict[str, object] | None = None,
        sample_items_json: dict[str, object] | None = None,
        checked_at: datetime | None = None,
    ) -> DiagnosticRun:
        run = self.repository.get_run(run_id)
        run.status = "completed"
        run.health_state = health_state
        run.summary_json = summary_json
        run.sample_items_json = sample_items_json
        run.checked_at = checked_at or utc_now()
        run.finished_at = utc_now()
        run.error_message = None
        saved = self.repository.save_run(run)
        self.apply_retention(diagnostic_key=saved.diagnostic_key)
        return saved

    def mark_run_failed(self, run_id: UUID, *, error_message: str) -> DiagnosticRun:
        run = self.repository.get_run(run_id)
        run.status = "failed"
        run.error_message = error_message
        run.finished_at = utc_now()
        saved = self.repository.save_run(run)
        self.apply_retention(diagnostic_key=saved.diagnostic_key)
        return saved

    def store_items(
        self,
        *,
        run_id: UUID,
        items: list[dict[str, object]],
    ) -> None:
        self.repository.add_run_items(diagnostic_run_id=run_id, items=items)

    def apply_retention(self, *, diagnostic_key: str) -> None:
        runs = self.repository.list_runs_for_retention(diagnostic_key=diagnostic_key)
        if len(runs) <= 3:
            return
        self.repository.delete_runs(runs[3:])


def get_system_integrity_service(
    session: Session = Depends(get_session),
) -> SystemIntegrityService:
    return SystemIntegrityService(session)
