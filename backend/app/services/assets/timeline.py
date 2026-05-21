from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.models import Asset
from app.services.assets.media import is_supported_video_mime_type


def asset_media_kind(mime_type: str) -> str:
    return "video" if is_supported_video_mime_type(mime_type) else "image"


def _normalize_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def parse_captured_at_local_day(value: str | None) -> date | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    normalized = normalized.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


@dataclass(frozen=True)
class AssetTimelineFields:
    media_kind: str
    timeline_at: datetime
    timeline_day: date
    timeline_month: date


def derive_asset_timeline_fields(
    *,
    mime_type: str,
    captured_at: datetime | None,
    captured_at_local: str | None,
    created_at: datetime | None,
) -> AssetTimelineFields:
    timeline_at = _normalize_timestamp(captured_at or created_at)
    timeline_day = parse_captured_at_local_day(captured_at_local) or timeline_at.date()
    return AssetTimelineFields(
        media_kind=asset_media_kind(mime_type),
        timeline_at=timeline_at,
        timeline_day=timeline_day,
        timeline_month=timeline_day.replace(day=1),
    )


def apply_asset_timeline_fields(asset: Asset) -> Asset:
    fields = derive_asset_timeline_fields(
        mime_type=asset.mime_type,
        captured_at=asset.captured_at,
        captured_at_local=asset.captured_at_local,
        created_at=asset.created_at,
    )
    asset.media_kind = fields.media_kind
    asset.timeline_at = fields.timeline_at
    asset.timeline_day = fields.timeline_day
    asset.timeline_month = fields.timeline_month
    return asset
