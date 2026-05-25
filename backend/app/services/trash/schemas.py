from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlmodel import Field, SQLModel


TrashSort = Literal[
    "deleted_at_desc",
    "deleted_at_asc",
    "taken_at_desc",
    "taken_at_asc",
]


class TrashTagSummary(SQLModel):
    id: int
    name: str
    path: str


class TrashPersonSummary(SQLModel):
    id: UUID | None = None
    name: str | None = None


class TrashFaceSummary(SQLModel):
    id: UUID
    person: TrashPersonSummary | None = None


class TrashAssetItem(SQLModel):
    id: UUID
    deleted_at: datetime
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    blurhash: str | None = None
    tags: list[TrashTagSummary] = Field(default_factory=list)
    faces: list[TrashFaceSummary] = Field(default_factory=list)


class TrashAssetListResponse(SQLModel):
    items: list[TrashAssetItem]
    page: int
    page_size: int
    total: int


class TrashAssetDetailResponse(SQLModel):
    id: UUID
    file_hash: str
    master_path: str
    mime_type: str
    deleted_at: datetime
    captured_at: datetime | None = None
    captured_at_local: str | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    file_size_bytes: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    duration_seconds: float | None = None
    preview_status: str | None = None
    blurhash: str | None = None
    exif_data: dict[str, object] | None = None
    tags: list[TrashTagSummary] = Field(default_factory=list)
    people: list[TrashPersonSummary] = Field(default_factory=list)
    faces: list[TrashFaceSummary] = Field(default_factory=list)
    small_thumbnail_url: str
    preview_url: str
    created_at: datetime


class RestoredAssetDetailResponse(SQLModel):
    id: UUID
    file_hash: str
    master_path: str
    mime_type: str
    captured_at: datetime | None = None
    captured_at_local: str | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    file_size_bytes: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    duration_seconds: float | None = None
    preview_status: str | None = None
    blurhash: str | None = None
    exif_data: dict[str, object] | None = None
    tags: list[TrashTagSummary] = Field(default_factory=list)
    people: list[TrashPersonSummary] = Field(default_factory=list)
    faces: list[TrashFaceSummary] = Field(default_factory=list)
    small_thumbnail_url: str
    preview_url: str
    created_at: datetime


class TrashRestoreJobSummary(SQLModel):
    queued_metadata_job: bool = False
    queued_embedding_job: bool = False
    queued_face_job: bool = False
    ran_face_matching: bool = False
    matched_faces: int = 0


class TrashRestoreResponse(SQLModel):
    asset: RestoredAssetDetailResponse
    jobs: TrashRestoreJobSummary


class TrashBulkRestoreRequest(SQLModel):
    asset_ids: list[UUID]


class TrashRestoreFailure(SQLModel):
    asset_id: UUID
    detail: str


class TrashBulkRestoreResponse(SQLModel):
    requested: int
    restored: int
    failed: int
    items: list[TrashRestoreResponse] = Field(default_factory=list)
    failures: list[TrashRestoreFailure] = Field(default_factory=list)


class TrashBulkDeleteRequest(SQLModel):
    asset_ids: list[UUID]


class TrashDeleteFailure(SQLModel):
    asset_id: UUID
    detail: str


class TrashDeleteSummaryResponse(SQLModel):
    requested: int
    deleted: int
    failed: int
    failures: list[TrashDeleteFailure] = Field(default_factory=list)


class TrashEmptyResponse(SQLModel):
    deleted: int
    failed: int
    failures: list[TrashDeleteFailure] = Field(default_factory=list)
