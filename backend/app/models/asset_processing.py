from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import utc_now


class AssetProcessing(SQLModel, table=True):
    __tablename__ = "asset_processing"
    __table_args__ = (
        Index(
            "uq_asset_processing_asset_task_null_model",
            "asset_id",
            "task",
            unique=True,
            postgresql_where=text("ai_model_id IS NULL"),
        ),
        Index(
            "uq_asset_processing_asset_model_task",
            "asset_id",
            "ai_model_id",
            "task",
            unique=True,
            postgresql_where=text("ai_model_id IS NOT NULL"),
        ),
        Index(
            "idx_asset_processing_task_model_status",
            "task",
            "ai_model_id",
            "status",
        ),
        Index("idx_asset_processing_asset_task", "asset_id", "task"),
        Index("idx_asset_processing_last_job_id", "last_job_id"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    asset_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    ai_model_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("ai_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    task: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(sa_column=Column(Text, nullable=False))
    output_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    last_job_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    processed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
            onupdate=utc_now,
        ),
    )
