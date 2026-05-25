from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlmodel import Field, SQLModel

from .common import Vector, utc_now


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
