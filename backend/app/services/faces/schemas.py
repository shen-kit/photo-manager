from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel


class FaceBoundingBoxRead(SQLModel):
    x: int
    y: int
    width: int
    height: int
    image_width: int
    image_height: int


class AssetFaceRead(SQLModel):
    id: UUID
    asset_id: UUID | None = None
    person_id: UUID | None = None
    bounding_box: FaceBoundingBoxRead | None = None
    detection_confidence: float | None = None
    crop_path: str | None = None
    crop_url: str | None = None
    is_confirmed: bool
    is_excluded: bool
    created_at: datetime
    updated_at: datetime


class FaceUpdateRequest(SQLModel):
    person_id: UUID | None = None
    is_confirmed: bool | None = None
    is_excluded: bool | None = None
