from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class JobCreate(SQLModel):
    type: str
    job_key: str | None = None
    parameters: dict[str, Any] | None = None
    progress_total: int | None = None
    parent_job_id: UUID | None = None
    related_asset_id: UUID | None = None
    is_visible: bool = True


class JobUpdate(SQLModel):
    status: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_message: str | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobRead(SQLModel):
    id: UUID
    type: str
    job_key: str | None = None
    status: str
    progress_current: int
    progress_total: int | None = None
    progress_message: str | None = None
    parameters: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    parent_job_id: UUID | None = None
    related_asset_id: UUID | None = None
    is_visible: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobChildCounts(SQLModel):
    total: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int


class JobDetailRead(JobRead):
    child_counts: JobChildCounts | None = None
    children: list[JobRead] = Field(default_factory=list)
