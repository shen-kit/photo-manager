from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, desc
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
        UniqueConstraint("model_name", "version_tag", name="uq_ai_models_model_name_version_tag"),
    )

    id: int | None = Field(default=None, primary_key=True)
    model_name: str = Field(sa_column=Column(Text, nullable=False))
    version_tag: str = Field(sa_column=Column(Text, nullable=False))
    vector_dimensions: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class Asset(SQLModel, table=True):
    __tablename__ = "assets"
    __table_args__ = (
        Index("idx_assets_captured_at", desc("captured_at")),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, nullable=False),
    )
    file_hash: str = Field(sa_column=Column(Text, unique=True, nullable=False))
    master_path: str = Field(sa_column=Column(Text, nullable=False))
    mime_type: str = Field(sa_column=Column(Text, nullable=False))
    captured_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    width: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    height: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    file_size_bytes: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    search_vector: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(512), nullable=True),
    )
    search_model_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("ai_models.id"), nullable=True),
    )
    blurhash: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
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
    is_hidden: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )


class Face(SQLModel, table=True):
    __tablename__ = "faces"

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
    is_confirmed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    is_excluded: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )


class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    __table_args__ = (
        Index("idx_tags_path_gist", "path", postgresql_using="gist"),
    )

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
