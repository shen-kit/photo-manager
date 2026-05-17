from __future__ import annotations

import json
import imghdr
import mimetypes
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
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

MEDIA_ORIGINALS_DIR = Path(
    os.getenv("MEDIA_ORIGINALS_DIR", "/media/originals")
).resolve()
MEDIA_PROCESSED_DIR = Path(
    os.getenv("MEDIA_PROCESSED_DIR", "/media/processed")
).resolve()
MEDIA_ORIGINALS_TMP_DIR = MEDIA_ORIGINALS_DIR / ".tmp"
THUMBNAIL_SPECS: dict[str, int] = {
    "tiny": 128,
    "small": 300,
    "large": 2000,
}
WEBP_QUALITY = 80
SMALL_THUMBNAIL_MAX_API_FILE_SIZE_BYTES = 10 * 1024 * 1024
LARGE_PREVIEW_MIN_MEGAPIXELS = 15
SUPPORTED_IMAGE_MIME_PREFIX = "image/"
SUPPORTED_VIDEO_MIME_PREFIX = "video/"
VIDEO_PREVIEW_STATUS_PENDING = "pending"
VIDEO_PREVIEW_STATUS_PROCESSING = "processing"
VIDEO_PREVIEW_STATUS_READY = "ready"
VIDEO_PREVIEW_STATUS_FAILED = "failed"
VIDEO_PREVIEW_MAX_WIDTH = 1280
VIDEO_PREVIEW_MAX_HEIGHT = 720


@dataclass(frozen=True)
class MediaInspection:
    width: int | None
    height: int | None
    video_codec: str | None = None
    audio_codec: str | None = None
    duration_seconds: float | None = None


def _normalize_relative_path(path: Path) -> str:
    normalized = path.as_posix().lstrip("/")
    if normalized.startswith("../") or normalized == "..":
        raise ValueError("File path must stay within the media library roots")
    return normalized


def _resolve_within(root: Path, relative_path: Path) -> Path:
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Resolved file path escapes the media library root") from exc
    return resolved


def is_supported_media_mime_type(mime_type: str) -> bool:
    return mime_type.startswith(SUPPORTED_IMAGE_MIME_PREFIX) or mime_type.startswith(
        SUPPORTED_VIDEO_MIME_PREFIX
    )


def is_supported_image_mime_type(mime_type: str) -> bool:
    return mime_type.startswith(SUPPORTED_IMAGE_MIME_PREFIX)


def is_supported_video_mime_type(mime_type: str) -> bool:
    return mime_type.startswith(SUPPORTED_VIDEO_MIME_PREFIX)


def guess_mime_type(path: Path, uploaded_content_type: str | None = None) -> str:
    if uploaded_content_type and uploaded_content_type != "application/octet-stream":
        return uploaded_content_type
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    detected = imghdr.what(path)
    return f"image/{detected}" if detected else "application/octet-stream"


def master_path_to_source_path(master_path: str) -> Path:
    normalized = _normalize_relative_path(Path(master_path))
    relative_path = Path(normalized)
    return _resolve_within(MEDIA_ORIGINALS_DIR, relative_path)


def source_path_to_master_path(source_path: Path) -> str:
    resolved = source_path.resolve()

    try:
        original_relative = resolved.relative_to(MEDIA_ORIGINALS_DIR)
    except ValueError:
        original_relative = None
    if original_relative is not None:
        return _normalize_relative_path(original_relative)
    raise ValueError("Source path must resolve within the originals media root")


def resolve_source_input(file_path: str) -> tuple[str, Path]:
    candidate = Path(file_path)

    if candidate.is_absolute():
        resolved = candidate.resolve()
        master_path = source_path_to_master_path(resolved)
    else:
        normalized = _normalize_relative_path(candidate)
        relative_path = Path(normalized)
        resolved = _resolve_within(MEDIA_ORIGINALS_DIR, relative_path)
        master_path = normalized

    if not resolved.is_file():
        raise FileNotFoundError("Original file was not found")

    return master_path, resolved


def is_temporary_original_path(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(MEDIA_ORIGINALS_DIR)
    except ValueError:
        return False
    return relative.parts[:1] == (".tmp",)


def canonical_original_path(file_hash: str, suffix: str) -> Path:
    normalized_suffix = suffix.lower()
    now = datetime.now(timezone.utc)
    return (
        MEDIA_ORIGINALS_DIR
        / now.strftime("%Y")
        / now.strftime("%m")
        / f"{file_hash}{normalized_suffix}"
    )


def is_canonical_hashed_original(path: Path, file_hash: str) -> bool:
    try:
        relative = path.resolve().relative_to(MEDIA_ORIGINALS_DIR)
    except ValueError:
        return False
    if len(relative.parts) == 0:
        return False
    if relative.parts[:1] == (".tmp",):
        return False
    return relative.stem == file_hash


def processed_asset_dir(asset_id: UUID) -> Path:
    return MEDIA_PROCESSED_DIR / "assets" / str(asset_id)


def processed_video_preview_path(asset_id: UUID) -> Path:
    return processed_asset_dir(asset_id) / "preview.mp4"


def validate_supported_image(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.load()
            return image.width, image.height
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unsupported image file") from exc


def _probe_media(path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout or "{}")


def inspect_video(path: Path) -> MediaInspection:
    try:
        payload = _probe_media(path)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise ValueError("Unsupported video file") from exc

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ValueError("Unsupported video file")

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        raise ValueError("Unsupported video file")

    audio_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )

    width = video_stream.get("width")
    height = video_stream.get("height")
    format_payload = payload.get("format")
    duration_raw = (
        format_payload.get("duration") if isinstance(format_payload, dict) else None
    )
    try:
        duration_seconds = (
            max(float(duration_raw), 0.0) if duration_raw is not None else None
        )
    except (TypeError, ValueError):
        duration_seconds = None

    return MediaInspection(
        width=width if isinstance(width, int) else None,
        height=height if isinstance(height, int) else None,
        video_codec=video_stream.get("codec_name")
        if isinstance(video_stream.get("codec_name"), str)
        else None,
        audio_codec=audio_stream.get("codec_name")
        if isinstance(audio_stream, dict)
        and isinstance(audio_stream.get("codec_name"), str)
        else None,
        duration_seconds=duration_seconds,
    )


def validate_supported_media(
    path: Path, mime_type: str
) -> tuple[int | None, int | None]:
    if not is_supported_media_mime_type(mime_type):
        raise ValueError("Only image and video files are supported")
    if is_supported_image_mime_type(mime_type):
        width, height = validate_supported_image(path)
        return width, height
    if is_supported_video_mime_type(mime_type):
        inspection = inspect_video(path)
        return inspection.width, inspection.height
    return None, None


def generate_blurhash_from_image(image: PILImage) -> str | None:
    try:
        import numpy as np
        from blurhash import encode

        rgb_image = image.convert("RGB").resize((64, 64))
        return encode(np.asarray(rgb_image))
    except Exception:
        return None


def should_generate_small_in_api(mime_type: str, file_size_bytes: int) -> bool:
    return (
        mime_type in {"image/jpeg", "image/png"}
        and file_size_bytes < SMALL_THUMBNAIL_MAX_API_FILE_SIZE_BYTES
    )


def should_generate_large_preview(width: int | None, height: int | None) -> bool:
    if width is None or height is None:
        return False
    megapixels = (width * height) / 1_000_000
    return megapixels > LARGE_PREVIEW_MIN_MEGAPIXELS


def _extract_middle_video_frame(video_path: Path) -> PILImage:
    duration_seconds = inspect_video(video_path).duration_seconds or 0.0
    midpoint_seconds = duration_seconds / 2 if duration_seconds > 0 else 0.0

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{midpoint_seconds:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-y",
                str(temp_path),
            ],
            check=True,
        )
        with Image.open(temp_path) as frame:
            return frame.convert("RGB").copy()
    finally:
        temp_path.unlink(missing_ok=True)


def _load_preview_image(original_path: Path, mime_type: str) -> PILImage:
    if is_supported_video_mime_type(mime_type):
        return _extract_middle_video_frame(original_path)

    with Image.open(original_path) as image:
        return ImageOps.exif_transpose(image).convert("RGB").copy()


def write_asset_variants(
    original_path: Path, asset_id: UUID, variants: tuple[str, ...], mime_type: str
) -> None:
    output_dir = processed_asset_dir(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized = _load_preview_image(original_path, mime_type)
    for variant in variants:
        max_size = THUMBNAIL_SPECS[variant]
        rendered = normalized.copy()
        rendered.thumbnail((max_size, max_size))
        rendered.save(
            output_dir / f"{variant}.webp", format="WEBP", quality=WEBP_QUALITY
        )


def write_video_preview(original_path: Path, asset_id: UUID) -> None:
    output_dir = processed_asset_dir(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = processed_video_preview_path(asset_id)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(original_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            f"scale=w={VIDEO_PREVIEW_MAX_WIDTH}:h={VIDEO_PREVIEW_MAX_HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-y",
            str(preview_path),
        ],
        check=True,
    )


def build_fast_variants(
    original_path: Path, asset_id: UUID, *, include_small: bool, mime_type: str
) -> str | None:
    output_dir = processed_asset_dir(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized = _load_preview_image(original_path, mime_type)
    blurhash_value = generate_blurhash_from_image(normalized)
    rendered = normalized.copy()
    rendered.thumbnail((THUMBNAIL_SPECS["tiny"], THUMBNAIL_SPECS["tiny"]))
    rendered.save(output_dir / "tiny.webp", format="WEBP", quality=WEBP_QUALITY)
    if include_small:
        small = normalized.copy()
        small.thumbnail((THUMBNAIL_SPECS["small"], THUMBNAIL_SPECS["small"]))
        small.save(output_dir / "small.webp", format="WEBP", quality=WEBP_QUALITY)
    return blurhash_value
