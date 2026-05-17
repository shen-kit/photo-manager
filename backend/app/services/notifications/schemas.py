from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import SQLModel

from .types import NotificationCategory, NotificationLevel


class NotificationCreate(SQLModel):
    level: NotificationLevel
    category: NotificationCategory
    title: str
    message: str | None = None
    details: dict[str, Any] | None = None
    related_job_id: UUID | None = None
    related_asset_id: UUID | None = None


class NotificationUpdate(SQLModel):
    read_at: datetime | None = None


class NotificationRead(SQLModel):
    id: UUID
    level: NotificationLevel
    category: NotificationCategory
    title: str
    message: str | None = None
    details: dict[str, Any] | None = None
    related_job_id: UUID | None = None
    related_asset_id: UUID | None = None
    created_at: datetime
    read_at: datetime | None = None
