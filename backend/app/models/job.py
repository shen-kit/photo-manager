from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Text, desc, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import utc_now


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_type", "type"),
        Index("idx_jobs_job_key_status", "job_key", "status"),
        Index("idx_jobs_queue_name_status", "queue_name", "status"),
        Index("idx_jobs_dedup_key_status", "dedup_key", "status"),
        Index("idx_jobs_parent_job_id_created_at", "parent_job_id", desc("created_at")),
        Index("idx_jobs_related_asset_id", "related_asset_id"),
        Index(
            "uq_jobs_parent_related_asset",
            "parent_job_id",
            "related_asset_id",
            unique=True,
            postgresql_where=text(
                "parent_job_id IS NOT NULL AND related_asset_id IS NOT NULL"
            ),
        ),
        Index("idx_jobs_created_at", desc("created_at")),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    type: str = Field(sa_column=Column(Text, nullable=False))
    job_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    queue_name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    intent: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    dedup_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    params_hash: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(sa_column=Column(Text, nullable=False))
    progress_current: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    progress_total: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    progress_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    parameters: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    parent_job_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    related_asset_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    is_visible: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
