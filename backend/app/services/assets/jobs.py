from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from PIL import Image, ImageOps
from sqlmodel import Session

from app.core.database import engine
from app.models import Asset
from app.services.assets.batching import (
    EmbeddingBatchProcessor,
    FaceBatchProcessor,
    ThumbnailBatchProcessor,
    parse_batch_items,
)
from app.services.assets.media import (
    VIDEO_PREVIEW_STATUS_PENDING,
    inspect_video,
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    master_path_to_source_path,
)
from app.services.assets.preview import AssetPreviewService
from app.services.assets.preview import IMAGE_PREVIEW_TASK, VIDEO_PREVIEW_TASK
from app.services.assets.timeline import apply_asset_timeline_fields
from app.services.jobs.context import JobNotification, JobTaskContext
from app.services.jobs.queue import enqueue_asset_embedding_job, enqueue_asset_faces_job
from app.services.notifications.types import NotificationCategory, NotificationLevel
from app.services.asset_processing.service import AssetProcessingTrackerService

EXIF_DATETIME_TAGS = ("36867", "306")
EXIF_OFFSET_TAGS = ("36881", "36880", "36882")
logger = logging.getLogger(__name__)


def _extract_exif_data(image: Image.Image) -> dict[str, str]:
    exif = image.getexif()
    if not exif:
        return {}
    return {str(tag_id): str(value) for tag_id, value in exif.items()}


def _parse_captured_timestamps(
    exif_data: dict[str, str],
) -> tuple[datetime | None, str | None]:
    raw_timestamp = next(
        (exif_data[tag] for tag in EXIF_DATETIME_TAGS if exif_data.get(tag)),
        None,
    )
    if raw_timestamp is None:
        return None, None
    try:
        local_naive = datetime.strptime(raw_timestamp, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, None

    raw_offset = next(
        (exif_data[tag].strip() for tag in EXIF_OFFSET_TAGS if exif_data.get(tag)),
        None,
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


async def process_asset_metadata(
    _: dict[str, object],
    asset_id: str,
    job_id: str | None = None,
    parent_job_id: str | None = None,
    enqueue_embedding: bool = True,
    enqueue_faces: bool = True,
) -> None:
    del parent_job_id
    asset_uuid = UUID(asset_id)
    job_uuid = UUID(job_id) if job_id else None
    with Session(engine) as session:
        job_context = JobTaskContext(session, job_id=job_uuid)
        thumbnail_processor = ThumbnailBatchProcessor(session)
        job_context.mark_running("Processing asset metadata")
        asset = session.get(Asset, asset_uuid)
        if asset is None:
            job_context.fail(
                "The asset no longer exists for metadata processing.",
                result={"asset_id": asset_id, "skipped": False},
            )
            return
        try:
            source_path = master_path_to_source_path(asset.master_path)
            if not source_path.is_file():
                raise FileNotFoundError(f"Source file missing for asset {asset.id}")
            if is_supported_video_mime_type(asset.mime_type):
                asset.exif_data = None
                video_metadata = inspect_video(source_path)
                asset.width = video_metadata.width
                asset.height = video_metadata.height
                asset.video_codec = video_metadata.video_codec
                asset.audio_codec = video_metadata.audio_codec
                asset.duration_seconds = video_metadata.duration_seconds
                asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
            else:
                with Image.open(source_path) as image:
                    normalized = ImageOps.exif_transpose(image)
                    exif_data = _extract_exif_data(normalized)
                asset.exif_data = exif_data or None
                parsed_captured_at, parsed_captured_at_local = (
                    _parse_captured_timestamps(exif_data)
                )
                if asset.captured_at is None and parsed_captured_at is not None:
                    asset.captured_at = parsed_captured_at
                if (
                    asset.captured_at_local is None
                    and parsed_captured_at_local is not None
                ):
                    asset.captured_at_local = parsed_captured_at_local
            apply_asset_timeline_fields(asset)
            session.add(asset)
            session.commit()
            thumbnail_processor.ensure_asset_thumbnails(asset.id)
        except Exception as exc:
            logger.warning(
                "Asset metadata processing failed for %s: %s", asset_uuid, exc
            )
            job_context.fail(
                str(exc),
                result={"asset_id": asset_id, "skipped": False},
                notification=JobNotification(
                    level=NotificationLevel.ERROR,
                    category=NotificationCategory.ASSET,
                    title="Asset processing failed",
                    message=str(exc),
                    details={"asset_id": asset_id},
                    related_asset_id=asset_uuid,
                ),
            )
            return

        queued_embedding_job = False
        queued_face_job = False
        if enqueue_embedding:
            queued_embedding_job = await enqueue_asset_embedding_job(asset.id)
        if enqueue_faces and is_supported_image_mime_type(asset.mime_type):
            queued_face_job = await enqueue_asset_faces_job(asset.id)
        job_context.complete(
            "Asset metadata processed",
            result={
                "asset_id": asset_id,
                "processed": True,
                "skipped": False,
                "queued_embedding_job": queued_embedding_job,
                "queued_face_job": queued_face_job,
            },
        )


async def process_asset_thumbnail_batch(
    _: dict[str, object],
    items: list[dict[str, str | None]],
) -> None:
    parsed_items = parse_batch_items(items)
    with Session(engine) as session:
        processor = ThumbnailBatchProcessor(session)
        results = processor.process_batch(parsed_items)
        for item in parsed_items:
            if item.job_id is None:
                continue
            job_context = JobTaskContext(session, job_id=item.job_id)
            error = results[item.asset_id]
            if error is None:
                job_context.complete(
                    "Asset thumbnails processed",
                    result={"asset_id": str(item.asset_id), "skipped": False},
                )
            else:
                job_context.fail(
                    str(error),
                    result={"asset_id": str(item.asset_id), "skipped": False},
                )


async def generate_asset_preview(
    _: dict[str, object],
    asset_id: str,
    job_id: str | None = None,
    priority: str = "low",
) -> None:
    del priority
    asset_uuid = UUID(asset_id)
    job_uuid = UUID(job_id) if job_id else None
    with Session(engine) as session:
        job_context = JobTaskContext(session, job_id=job_uuid)
        service = AssetPreviewService(session)
        tracker = AssetProcessingTrackerService(session)
        job_context.mark_running("Generating asset preview")
        try:
            asset = session.get(Asset, asset_uuid)
            if asset is None:
                raise RuntimeError(f"Asset {asset_id} not found")
            task = (
                VIDEO_PREVIEW_TASK
                if is_supported_video_mime_type(asset.mime_type)
                else IMAGE_PREVIEW_TASK
            )
            tracker.mark_running(
                asset_id=asset_uuid,
                ai_model_id=None,
                task=task,
                job_id=job_uuid,
            )
            if is_supported_video_mime_type(asset.mime_type):
                preview_path = service.generate_video_preview(asset_uuid)
            else:
                preview_path = service.generate_image_preview(asset_uuid)
        except Exception as exc:
            logger.warning(
                "Preview generation failed for asset %s: %s", asset_uuid, exc
            )
            if "task" in locals():
                tracker.mark_failed(
                    asset_id=asset_uuid,
                    ai_model_id=None,
                    task=task,
                    job_id=job_uuid,
                    error_message=str(exc),
                )
            job_context.fail(
                str(exc),
                result={"asset_id": asset_id, "skipped": False},
                notification=JobNotification(
                    level=NotificationLevel.ERROR,
                    category=NotificationCategory.ASSET,
                    title="Preview generation failed",
                    message=str(exc),
                    details={"asset_id": asset_id},
                    related_asset_id=asset_uuid,
                ),
            )
            return
        tracker.mark_completed(
            asset_id=asset_uuid,
            ai_model_id=None,
            task=task,
            job_id=job_uuid,
            output_count=1,
        )
        job_context.complete(
            "Asset preview generated",
            result={"asset_id": asset_id, "preview_path": str(preview_path)},
        )
