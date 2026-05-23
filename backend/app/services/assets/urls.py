from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from app.models import Asset
from app.services.assets.media import is_supported_video_mime_type


def build_thumbnail_url(base_url: str, asset_id: UUID, variant: str) -> str:
    del base_url
    return f"/media/processed/assets/{asset_id}/{variant}.webp"


def build_preview_url(base_url: str, asset: Asset) -> str:
    del base_url
    return preview_relative_url(asset)


def preview_relative_url(asset: Asset) -> str:
    if is_supported_video_mime_type(asset.mime_type):
        return f"/media/processed/assets/{asset.id}/preview.mp4"
    if asset.has_large_preview:
        return f"/media/processed/assets/{asset.id}/large.webp"
    return f"/media/originals/{quote(asset.master_path, safe='/')}"
