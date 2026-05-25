from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import Ltree, utc_now


class Tag(SQLModel, table=True):
    __tablename__ = "tags"
    __table_args__ = (
        Index("idx_tags_path_gist", "path", postgresql_using="gist"),
        Index("idx_tags_is_album", "is_album"),
        Index("idx_tags_cover_asset_id", "cover_asset_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, nullable=False))
    path: str = Field(sa_column=Column(Ltree(), unique=True, nullable=False))
    is_album: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cover_asset_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("assets.id", ondelete="SET NULL"),
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
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
            onupdate=utc_now,
        ),
    )


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
