from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


class PersonSummary(SQLModel):
    id: UUID | None = None
    name: str | None = None


class FaceSummary(SQLModel):
    id: UUID
    person: PersonSummary | None = None


class TagSummary(SQLModel):
    id: int
    name: str
    path: str


class PersonRead(SQLModel):
    id: UUID
    name: str | None = None
    thumbnail_face_id: UUID | None = None
    thumbnail_crop_path: str | None = None
    thumbnail_crop_url: str | None = None
    face_count: int
    asset_count: int
    is_hidden: bool


class PersonUpdateRequest(SQLModel):
    name: str | None = None
    is_hidden: bool | None = None
    thumbnail_face_id: UUID | None = None


class PersonAssetItem(SQLModel):
    id: UUID
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    blurhash: str | None = None
    tags: list[TagSummary] = Field(default_factory=list)
    faces: list[FaceSummary] = Field(default_factory=list)


class PersonAssetListResponse(SQLModel):
    items: list[PersonAssetItem]
    page: int
    page_size: int
    total: int


class PersonMergeResponse(SQLModel):
    faces_moved: int
    source_deleted: bool
    target_person_id: UUID
