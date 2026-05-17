from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import SQLModel


class JobCreate(SQLModel):
    type: str
    parameters: dict[str, Any] | None = None
    progress_total: int | None = None


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
    status: str
    progress_current: int
    progress_total: int | None = None
    progress_message: str | None = None
    parameters: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
