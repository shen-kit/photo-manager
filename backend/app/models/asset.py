from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, Text, desc, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import Vector, utc_now


class Asset(SQLModel, table=True):
    __tablename__ = "assets"
    __table_args__ = (
        Index("idx_assets_captured_at", desc("captured_at")),
        Index(
            "idx_assets_active_timeline_desc",
            desc("timeline_at"),
            desc("id"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_assets_active_month_timeline_desc",
            "timeline_month",
            desc("timeline_at"),
            desc("id"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_assets_active_day_timeline_desc",
            "timeline_day",
            desc("timeline_at"),
            desc("id"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_assets_active_media_timeline_desc",
            "media_kind",
            desc("timeline_at"),
            desc("id"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("uq_assets_file_hash", "file_hash", unique=True),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    file_hash: str = Field(sa_column=Column(Text, nullable=False))
    master_path: str = Field(sa_column=Column(Text, nullable=False))
    mime_type: str = Field(sa_column=Column(Text, nullable=False))
    media_kind: str = Field(
        default="image",
        sa_column=Column(Text, nullable=False, server_default=text("'image'")),
    )
    captured_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    captured_at_local: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_favorite: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    width: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    height: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    has_large_preview: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    file_size_bytes: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    video_codec: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    audio_codec: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    duration_seconds: float | None = Field(
        default=None, sa_column=Column(Float, nullable=True)
    )
    preview_status: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    exif_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    search_vector: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(512), nullable=True),
    )
    search_model_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("ai_models.id"), nullable=True),
    )
    blurhash: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    timeline_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )
    timeline_day: date = Field(
        default_factory=lambda: utc_now().date(),
        sa_column=Column(
            Date,
            nullable=False,
            server_default=text("CURRENT_DATE"),
        ),
    )
    timeline_month: date = Field(
        default_factory=lambda: utc_now().date().replace(day=1),
        sa_column=Column(
            Date,
            nullable=False,
            server_default=text("date_trunc('month', CURRENT_DATE)::date"),
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
