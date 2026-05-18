from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


class SearchTagSummary(SQLModel):
    id: int
    name: str
    path: str


class SearchPersonSummary(SQLModel):
    id: UUID | None = None
    name: str | None = None


class SearchFaceSummary(SQLModel):
    id: UUID
    person: SearchPersonSummary | None = None


class SearchResultItem(SQLModel):
    id: UUID
    captured_at: datetime | None = None
    description: str | None = None
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    blurhash: str | None = None
    score: float
    distance: float
    tags: list[SearchTagSummary] = Field(default_factory=list)
    faces: list[SearchFaceSummary] = Field(default_factory=list)


class SearchResponse(SQLModel):
    items: list[SearchResultItem]
    query: str
    limit: int
    offset: int
    total: int
