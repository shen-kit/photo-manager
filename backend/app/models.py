from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.types import Boolean, UserDefinedType
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"


class Ltree(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "ltree"


class AIModel(SQLModel, table=True):
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint(
            "task",
            "model_name",
            "version_tag",
            name="uq_ai_models_task_model_name_version_tag",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    task: str = Field(sa_column=Column(Text, nullable=False))
    model_name: str = Field(sa_column=Column(Text, nullable=False))
    version_tag: str = Field(sa_column=Column(Text, nullable=False))
    vector_dimensions: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )
    is_deprecated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )


class AIModelDefault(SQLModel, table=True):
    __tablename__ = "ai_model_defaults"

    task: str = Field(sa_column=Column(Text, primary_key=True, nullable=False))
    model_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("ai_models.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    )


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


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_type", "type"),
        Index("idx_jobs_job_key_status", "job_key", "status"),
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


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_level", "level"),
        Index("idx_notifications_category", "category"),
        Index("idx_notifications_created_at", desc("created_at")),
        Index("idx_notifications_read_at", "read_at"),
        Index("idx_notifications_related_job_id", "related_job_id"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    level: str = Field(sa_column=Column(Text, nullable=False))
    category: str = Field(sa_column=Column(Text, nullable=False))
    title: str = Field(sa_column=Column(Text, nullable=False))
    message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    details: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    related_job_id: UUID | None = Field(
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
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    read_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class Person(SQLModel, table=True):
    __tablename__ = "people"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    thumbnail_face_id: UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("faces.id"), nullable=True),
    )
    thumbnail_path: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    thumbnail_manually_set: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    is_hidden: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )


class Face(SQLModel, table=True):
    __tablename__ = "faces"
    __table_args__ = (
        Index("idx_faces_asset_id", "asset_id"),
        Index("idx_faces_person_id", "person_id"),
        Index(
            "idx_faces_person_asset_active",
            "person_id",
            "asset_id",
            postgresql_where=text(
                "is_excluded = false AND person_id IS NOT NULL AND asset_id IS NOT NULL"
            ),
        ),
        Index("idx_faces_face_model_id", "face_model_id"),
        Index(
            "idx_faces_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL AND is_excluded = false"),
        ),
        Index(
            "idx_faces_assigned_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text(
                "embedding IS NOT NULL AND is_excluded = false AND person_id IS NOT NULL"
            ),
        ),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    asset_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="CASCADE"),
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
    bounding_box: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(512), nullable=True),
    )
    face_model_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("ai_models.id"), nullable=True),
    )
    confidence: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    crop_path: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_confirmed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    is_excluded: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
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


class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    __table_args__ = (Index("idx_tags_path_gist", "path", postgresql_using="gist"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    path: str = Field(sa_column=Column(Ltree(), unique=True, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class AssetTag(SQLModel, table=True):
    __tablename__ = "asset_tags"

    asset_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    tag_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    username: str = Field(sa_column=Column(Text, unique=True, nullable=False))
    password_hash: str = Field(sa_column=Column(Text, nullable=False))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_expires_at", "expires_at"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    token_hash: str = Field(sa_column=Column(Text, unique=True, nullable=False))
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    replaced_by_token_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
