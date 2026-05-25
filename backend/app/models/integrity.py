from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Text, desc, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import utc_now


class DiagnosticRun(SQLModel, table=True):
    __tablename__ = "diagnostic_runs"
    __table_args__ = (
        Index("idx_diagnostic_runs_key_checked_at", "diagnostic_key", desc("checked_at")),
        Index("idx_diagnostic_runs_key_created_at", "diagnostic_key", desc("created_at")),
        Index("idx_diagnostic_runs_status", "status"),
        Index("idx_diagnostic_runs_related_job_id", "related_job_id"),
        Index("idx_diagnostic_runs_latest_repair_job_id", "latest_repair_job_id"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    diagnostic_key: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(sa_column=Column(Text, nullable=False))
    health_state: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    summary_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    sample_items_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    repair_job_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    related_job_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    latest_repair_job_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    requested_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    checked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class DiagnosticRunItem(SQLModel, table=True):
    __tablename__ = "diagnostic_run_items"
    __table_args__ = (
        Index("idx_diagnostic_run_items_run_id_id", "diagnostic_run_id", "id"),
        Index("idx_diagnostic_run_items_asset_id", "asset_id"),
        Index("idx_diagnostic_run_items_person_id", "person_id"),
        Index("idx_diagnostic_run_items_reason_code", "reason_code"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    diagnostic_run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("diagnostic_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    asset_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    person_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("people.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    relative_path: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    item_type: str = Field(sa_column=Column(Text, nullable=False))
    reason_code: str = Field(sa_column=Column(Text, nullable=False))
    repairable: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    detail_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )
