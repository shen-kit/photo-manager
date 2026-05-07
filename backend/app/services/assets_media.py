from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import Image as PILImage

try:
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - optional codec dependency
    register_heif_opener = None

if register_heif_opener is not None:
    register_heif_opener()

MEDIA_ORIGINALS_DIR = Path(os.getenv("MEDIA_ORIGINALS_DIR", "/media/originals")).resolve()
MEDIA_PROCESSED_DIR = Path(os.getenv("MEDIA_PROCESSED_DIR", "/media/processed")).resolve()
THUMBNAIL_SPECS: dict[str, int] = {
    "tiny": 128,
    "small": 300,
    "large": 2000,
}
WEBP_QUALITY = 80
SMALL_THUMBNAIL_MAX_API_FILE_SIZE_BYTES = 10 * 1024 * 1024
LARGE_PREVIEW_MIN_MEGAPIXELS = 15


def processed_asset_dir(asset_id: UUID) -> Path:
    return MEDIA_PROCESSED_DIR / "assets" / str(asset_id)


def validate_supported_image(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.load()
            return image.width, image.height
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unsupported image file") from exc


def generate_blurhash_from_image(image: PILImage) -> str | None:
    try:
        import numpy as np
        from blurhash import encode

        rgb_image = image.convert("RGB").resize((64, 64))
        return encode(np.asarray(rgb_image))
    except Exception:
        return None


def should_generate_small_in_api(mime_type: str, file_size_bytes: int) -> bool:
    return mime_type in {"image/jpeg", "image/png"} and file_size_bytes < SMALL_THUMBNAIL_MAX_API_FILE_SIZE_BYTES


def should_generate_large_preview(width: int | None, height: int | None) -> bool:
    if width is None or height is None:
        return False
    megapixels = (width * height) / 1_000_000
    return megapixels > LARGE_PREVIEW_MIN_MEGAPIXELS


def write_asset_variants(original_path: Path, asset_id: UUID, variants: tuple[str, ...]) -> None:
    output_dir = processed_asset_dir(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(original_path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        for variant in variants:
            max_size = THUMBNAIL_SPECS[variant]
            rendered = normalized.copy()
            rendered.thumbnail((max_size, max_size))
            rendered.save(output_dir / f"{variant}.webp", format="WEBP", quality=WEBP_QUALITY)


def build_fast_variants(original_path: Path, asset_id: UUID, *, include_small: bool) -> str | None:
    output_dir = processed_asset_dir(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(original_path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        blurhash_value = generate_blurhash_from_image(normalized)
        rendered = normalized.copy()
        rendered.thumbnail((THUMBNAIL_SPECS["tiny"], THUMBNAIL_SPECS["tiny"]))
        rendered.save(output_dir / "tiny.webp", format="WEBP", quality=WEBP_QUALITY)
        if include_small:
            small = normalized.copy()
            small.thumbnail((THUMBNAIL_SPECS["small"], THUMBNAIL_SPECS["small"]))
            small.save(output_dir / "small.webp", format="WEBP", quality=WEBP_QUALITY)
        return blurhash_value
