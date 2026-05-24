from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import SQLModel

from app.services.jobs.schemas import JobRead


class DiagnosticDefinitionRead(SQLModel):
    key: str
    title: str
    description: str
    supports_repair: bool
    repair_job_key: str | None = None
    latest_run_id: UUID | None = None
    latest_status: str | None = None
    latest_health_state: str | None = None
    latest_checked_at: datetime | None = None
    active_run_id: UUID | None = None


class DiagnosticRunItemRead(SQLModel):
    id: UUID
    diagnostic_run_id: UUID
    asset_id: UUID | None = None
    person_id: UUID | None = None
    relative_path: str | None = None
    item_type: str
    reason_code: str
    repairable: bool
    detail_json: dict[str, Any] | None = None
    created_at: datetime


class DiagnosticRunRead(SQLModel):
    id: UUID
    diagnostic_key: str
    status: str
    health_state: str | None = None
    summary_json: dict[str, Any] | None = None
    sample_items_json: dict[str, Any] | None = None
    error_message: str | None = None
    repair_job_key: str | None = None
    related_job_id: UUID | None = None
    latest_repair_job_id: UUID | None = None
    requested_by_user_id: UUID | None = None
    created_at: datetime
    started_at: datetime | None = None
    checked_at: datetime | None = None
    finished_at: datetime | None = None


class DiagnosticRunDetailRead(DiagnosticRunRead):
    related_job: JobRead | None = None
    latest_repair_job: JobRead | None = None


class DiagnosticRunListRead(SQLModel):
    items: list[DiagnosticRunRead]


class DiagnosticRunItemPageRead(SQLModel):
    items: list[DiagnosticRunItemRead]
    limit: int
    offset: int
    total: int


class DiagnosticDefinitionListRead(SQLModel):
    items: list[DiagnosticDefinitionRead]


class DiagnosticRunRequest(SQLModel):
    limit: int | None = None


class DiagnosticRepairRequest(SQLModel):
    limit: int | None = None


class DiagnosticRunResponse(SQLModel):
    run: DiagnosticRunRead

