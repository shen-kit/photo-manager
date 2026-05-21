from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlmodel import SQLModel


class SearchResultItem(SQLModel):
    id: UUID
    mime_type: str
    media_kind: str
    captured_at: datetime | None = None
    timeline_day: date
    is_favorite: bool
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    has_large_preview: bool
    small_thumbnail_url: str
    blurhash: str | None = None
    score: float
    distance: float


class SearchResponse(SQLModel):
    items: list[SearchResultItem]
    query: str
    next_cursor: str | None = None
    has_more: bool
