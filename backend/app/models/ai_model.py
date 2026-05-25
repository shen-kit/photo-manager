from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from .common import utc_now


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
