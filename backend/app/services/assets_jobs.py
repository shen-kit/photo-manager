from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps
from sqlmodel import Session

from app.core.database import engine
from app.models import Asset
from app.services.assets_media import (
    MEDIA_ORIGINALS_DIR,
    processed_asset_dir,
    should_generate_large_preview,
    should_generate_small_in_api,
    write_asset_variants,
)

EXIF_DATETIME_TAGS = ("36867", "306")
EXIF_OFFSET_TAGS = ("36881", "36880", "36882")
logger = logging.getLogger(__name__)


def _extract_exif_data(image: Image.Image) -> dict[str, str]:
    exif = image.getexif()
    if not exif:
        return {}

    extracted: dict[str, str] = {}
    for tag_id, value in exif.items():
        extracted[str(tag_id)] = str(value)
    return extracted


def _parse_captured_timestamps(exif_data: dict[str, str]) -> tuple[datetime | None, str | None]:
    raw_timestamp = next((exif_data[tag] for tag in EXIF_DATETIME_TAGS if exif_data.get(tag)), None)
    if raw_timestamp is None:
        return None, None

    try:
        local_naive = datetime.strptime(raw_timestamp, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, None

    raw_offset = next((exif_data[tag].strip() for tag in EXIF_OFFSET_TAGS if exif_data.get(tag)), None)
    if raw_offset:
        normalized_offset = raw_offset.replace("Z", "+00:00")
        try:
            local_with_offset = datetime.fromisoformat(f"{local_naive.isoformat()}{normalized_offset}")
        except ValueError:
            return local_naive.replace(tzinfo=UTC), local_naive.isoformat()
        return local_with_offset.astimezone(UTC), local_with_offset.isoformat()

    return local_naive.replace(tzinfo=UTC), local_naive.isoformat()


def _remove_large_preview(asset_id: UUID) -> None:
    large_path = processed_asset_dir(asset_id) / "large.webp"
    large_path.unlink(missing_ok=True)


def _run_clip_embeddings(asset: Asset) -> None:
    logger.info("CLIP embedding placeholder for asset %s", asset.id)


def _run_facial_recognition(asset: Asset) -> None:
    logger.info("Facial recognition placeholder for asset %s", asset.id)


async def process_asset_metadata(_: dict[str, object], asset_id: str) -> None:
    with Session(engine) as session:
        asset = session.get(Asset, UUID(asset_id))
        if asset is None:
            return

        original_path = (MEDIA_ORIGINALS_DIR / asset.master_path).resolve()
        try:
            original_path.relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError:
            return
        if not original_path.is_file():
            return

        try:
            with Image.open(original_path) as image:
                normalized = ImageOps.exif_transpose(image)
                exif_data = _extract_exif_data(normalized)
        except Exception:
            exif_data = {}

        asset.exif_data = exif_data or None
        parsed_captured_at, parsed_captured_at_local = _parse_captured_timestamps(exif_data)
        if asset.captured_at is None and parsed_captured_at is not None:
            asset.captured_at = parsed_captured_at
        if asset.captured_at_local is None and parsed_captured_at_local is not None:
            asset.captured_at_local = parsed_captured_at_local
        if not should_generate_small_in_api(asset.mime_type, asset.file_size_bytes or 0):
            write_asset_variants(original_path, asset.id, ("small",))

        asset.has_large_preview = should_generate_large_preview(asset.width, asset.height)
        if asset.has_large_preview:
            write_asset_variants(original_path, asset.id, ("large",))
        else:
            _remove_large_preview(asset.id)

        _run_clip_embeddings(asset)
        _run_facial_recognition(asset)

        session.add(asset)
        session.commit()
