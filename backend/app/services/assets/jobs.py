from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps
from sqlmodel import Session

from app.core.database import engine
from app.models import Asset
from app.services.jobs.queue import enqueue_asset_embedding_job
from app.services.jobs.queue import enqueue_asset_processing_job
from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel
from app.services.assets.media import (
    VIDEO_PREVIEW_STATUS_FAILED,
    VIDEO_PREVIEW_STATUS_PROCESSING,
    VIDEO_PREVIEW_STATUS_READY,
    build_fast_variants,
    inspect_video,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
    processed_video_preview_path,
    should_generate_large_preview,
    should_generate_small_in_api,
    write_asset_variants,
    write_video_preview,
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


def _parse_captured_timestamps(
    exif_data: dict[str, str],
) -> tuple[datetime | None, str | None]:
    raw_timestamp = next(
        (exif_data[tag] for tag in EXIF_DATETIME_TAGS if exif_data.get(tag)), None
    )
    if raw_timestamp is None:
        return None, None

    try:
        local_naive = datetime.strptime(raw_timestamp, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, None

    raw_offset = next(
        (exif_data[tag].strip() for tag in EXIF_OFFSET_TAGS if exif_data.get(tag)), None
    )
    if raw_offset:
        normalized_offset = raw_offset.replace("Z", "+00:00")
        try:
            local_with_offset = datetime.fromisoformat(
                f"{local_naive.isoformat()}{normalized_offset}"
            )
        except ValueError:
            return local_naive.replace(tzinfo=UTC), local_naive.isoformat()
        return local_with_offset.astimezone(UTC), local_with_offset.isoformat()

    return local_naive.replace(tzinfo=UTC), local_naive.isoformat()


def _remove_large_preview(asset_id: UUID) -> None:
    large_path = processed_asset_dir(asset_id) / "large.webp"
    large_path.unlink(missing_ok=True)


def _remove_video_preview(asset_id: UUID) -> None:
    processed_video_preview_path(asset_id).unlink(missing_ok=True)


def _ensure_fast_artifacts(asset: Asset, original_path: Path) -> None:
    include_small = is_supported_video_mime_type(
        asset.mime_type
    ) or should_generate_small_in_api(asset.mime_type, asset.file_size_bytes or 0)
    output_dir = processed_asset_dir(asset.id)
    tiny_path = output_dir / "tiny.webp"
    small_path = output_dir / "small.webp"

    if tiny_path.is_file() and asset.blurhash is not None:
        if not include_small or small_path.is_file():
            return

    asset.blurhash = build_fast_variants(
        original_path,
        asset.id,
        include_small=include_small,
        mime_type=asset.mime_type,
    )


def _update_parent_job_message(
    *, session: Session, related_job_id: UUID | None, message: str
) -> None:
    if related_job_id is None:
        return
    job_service = JobService(session)
    job = job_service.get_job(related_job_id)
    if job.status != "running":
        return
    job_service.update_progress(related_job_id, message=message)


async def process_asset_metadata(
    _: dict[str, object], asset_id: str, job_id: str | None = None
) -> None:
    related_job_id = UUID(job_id) if job_id else None
    with Session(engine) as session:
        notification_service = NotificationService(session)

        def notify_processing_error(
            *,
            message: str,
            asset_id_value: UUID | None = None,
            details: dict[str, str] | None = None,
        ) -> None:
            notification_service.create_notification(
                level=NotificationLevel.ERROR,
                category=NotificationCategory.ASSET,
                title="Asset processing failed",
                message=message,
                details=details,
                related_job_id=related_job_id,
                related_asset_id=asset_id_value,
            )

        asset = session.get(Asset, UUID(asset_id))
        if asset is None:
            logger.warning("Asset %s disappeared before metadata processing", asset_id)
            if related_job_id is not None:
                _update_parent_job_message(
                    session=session,
                    related_job_id=related_job_id,
                    message="A background asset could not be processed.",
                )
                notify_processing_error(
                    message="The asset no longer exists for metadata processing.",
                    details={"asset_id": asset_id},
                )
            return

        try:
            original_path = master_path_to_source_path(asset.master_path)
        except ValueError:
            logger.warning(
                "Asset %s has invalid master path %s", asset.id, asset.master_path
            )
            _update_parent_job_message(
                session=session,
                related_job_id=related_job_id,
                message="A background asset could not be processed.",
            )
            notify_processing_error(
                message="The asset source path is invalid.",
                asset_id_value=asset.id,
                details={"master_path": asset.master_path},
            )
            return
        if not original_path.is_file():
            logger.warning(
                "Asset %s source file is missing at %s", asset.id, original_path
            )
            _update_parent_job_message(
                session=session,
                related_job_id=related_job_id,
                message="A background asset could not be processed.",
            )
            notify_processing_error(
                message="The asset source file is missing.",
                asset_id_value=asset.id,
                details={"master_path": asset.master_path},
            )
            return

        if is_supported_video_mime_type(asset.mime_type):
            exif_data = {}
        else:
            try:
                with Image.open(original_path) as image:
                    normalized = ImageOps.exif_transpose(image)
                    exif_data = _extract_exif_data(normalized)
            except Exception:
                exif_data = {}

        asset.exif_data = exif_data or None
        parsed_captured_at, parsed_captured_at_local = _parse_captured_timestamps(
            exif_data
        )
        if asset.captured_at is None and parsed_captured_at is not None:
            asset.captured_at = parsed_captured_at
        if asset.captured_at_local is None and parsed_captured_at_local is not None:
            asset.captured_at_local = parsed_captured_at_local

        _ensure_fast_artifacts(asset, original_path)

        if is_supported_video_mime_type(asset.mime_type):
            try:
                video_metadata = inspect_video(original_path)
            except ValueError:
                asset.preview_status = VIDEO_PREVIEW_STATUS_FAILED
                _remove_video_preview(asset.id)
                session.add(asset)
                session.commit()
                _update_parent_job_message(
                    session=session,
                    related_job_id=related_job_id,
                    message="A background asset could not be processed.",
                )
                notify_processing_error(
                    message="Video metadata inspection failed.",
                    asset_id_value=asset.id,
                    details={"master_path": asset.master_path},
                )
                return
            asset.width = video_metadata.width
            asset.height = video_metadata.height
            asset.video_codec = video_metadata.video_codec
            asset.audio_codec = video_metadata.audio_codec
            asset.duration_seconds = video_metadata.duration_seconds
            asset.preview_status = VIDEO_PREVIEW_STATUS_PROCESSING
            session.add(asset)
            session.commit()
        if not should_generate_small_in_api(
            asset.mime_type, asset.file_size_bytes or 0
        ):
            write_asset_variants(original_path, asset.id, ("small",), asset.mime_type)

        asset.has_large_preview = should_generate_large_preview(
            asset.width, asset.height
        )
        if asset.has_large_preview:
            write_asset_variants(original_path, asset.id, ("large",), asset.mime_type)
        else:
            _remove_large_preview(asset.id)
        if is_supported_video_mime_type(asset.mime_type):
            try:
                write_video_preview(original_path, asset.id)
            except Exception:
                asset.preview_status = VIDEO_PREVIEW_STATUS_FAILED
                _remove_video_preview(asset.id)
                session.add(asset)
                session.commit()
                logger.exception(
                    "Failed to generate video preview for asset %s", asset.id
                )
                _update_parent_job_message(
                    session=session,
                    related_job_id=related_job_id,
                    message="A background asset could not be processed.",
                )
                notify_processing_error(
                    message="Video preview generation failed.",
                    asset_id_value=asset.id,
                    details={"master_path": asset.master_path},
                )
                return
            asset.preview_status = VIDEO_PREVIEW_STATUS_READY

        session.add(asset)
        session.commit()
        queued_embedding_job = await enqueue_asset_embedding_job(asset.id)
        if not queued_embedding_job:
            logger.warning(
                "Failed to enqueue CLIP embedding job for asset %s", asset.id
            )
            notification_service.create_notification(
                level=NotificationLevel.WARNING,
                category=NotificationCategory.SEARCH,
                title="Embedding job failed to queue",
                message="The asset metadata was processed, but semantic embedding generation was not queued.",
                related_job_id=related_job_id,
                related_asset_id=asset.id,
                details={"asset_id": str(asset.id)},
            )
