from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


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
