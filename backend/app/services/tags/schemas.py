from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel


class TagNode(SQLModel):
    id: int
    name: str
    slug: str
    path: str
    parent_path: str | None = None
    is_album: bool
    description: str | None = None
    cover_asset_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
