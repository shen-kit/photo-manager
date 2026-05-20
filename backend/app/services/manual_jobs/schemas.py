from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlmodel import SQLModel

from app.services.jobs.schemas import JobRead

ManualJobMode = Literal["global", "batched"]
ManualJobParameterType = Literal["boolean", "integer", "number"]


class ManualJobRunRequest(SQLModel):
    params: dict[str, Any] | None = None


class ManualJobParameterRead(SQLModel):
    name: str
    type: ManualJobParameterType
    required: bool = False
    default: Any | None = None
    description: str | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None


class ManualJobDefinitionRead(SQLModel):
    job_key: str
    title: str
    description: str
    category: str
    mode: ManualJobMode
    supports_dry_run: bool
    batch_size: int | None = None
    pending_count: int | None = None
    active_job_id: UUID | None = None
    active_status: str | None = None
    last_job_id: UUID | None = None
    last_status: str | None = None
    last_finished_at: datetime | None = None
    parameters: list[ManualJobParameterRead] = []
    default_params: dict[str, Any] = {}


class ManualJobCatalogRead(SQLModel):
    items: list[ManualJobDefinitionRead]


class ManualJobRunResponse(SQLModel):
    job: JobRead


class ManualJobConflictResponse(SQLModel):
    detail: str
    job_key: str
    active_job_id: UUID


class ManualJobRunPayload(SQLModel):
    params: dict[str, Any] = {}


class ManualJobBatchPayload(SQLModel):
    payload: dict[str, Any]
    asset_ids: list[UUID]
