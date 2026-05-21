from __future__ import annotations

from uuid import UUID

from sqlmodel import SQLModel


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
    thumbnail_path: str | None = None
    thumbnail_url: str | None = None
    thumbnail_manually_set: bool
    face_count: int
    asset_count: int
    is_hidden: bool


class PersonUpdateRequest(SQLModel):
    name: str | None = None
    is_hidden: bool | None = None
    thumbnail_face_id: UUID | None = None


class PersonThumbnailUpdateRequest(SQLModel):
    asset_id: UUID


class PersonMergeResponse(SQLModel):
    faces_moved: int
    source_deleted: bool
    target_person_id: UUID
