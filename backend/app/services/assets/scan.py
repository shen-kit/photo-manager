from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.database import engine
from app.models import Asset
from app.services.assets.batching import BatchProcessingItem, ThumbnailBatchProcessor
from app.services.assets.hashing import compute_sha256
from app.services.jobs.queue import (
    enqueue_asset_embedding_batch_job,
    enqueue_asset_faces_batch_job,
)
from app.services.jobs.dispatcher import INTENT_AI
from app.services.assets.media import (
    MEDIA_ORIGINALS_DIR,
    MEDIA_ORIGINALS_TMP_DIR,
    VIDEO_PREVIEW_STATUS_PENDING,
    guess_mime_type,
    inspect_video,
    is_supported_media_mime_type,
    is_supported_video_mime_type,
    should_generate_large_preview,
    source_path_to_master_path,
    validate_supported_media,
)
from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel

logger = logging.getLogger(__name__)
SCAN_BATCH_SIZE = 50


@dataclass(frozen=True)
class ScanStats:
    files_seen: int = 0
    supported_files_seen: int = 0
    created_assets: int = 0
    duplicates_skipped: int = 0
    unsupported_skipped: int = 0
    failed: int = 0
    processing_jobs_enqueued: int = 0

    def add(self, other: "ScanStats") -> "ScanStats":
        return ScanStats(
            files_seen=self.files_seen + other.files_seen,
            supported_files_seen=self.supported_files_seen + other.supported_files_seen,
            created_assets=self.created_assets + other.created_assets,
            duplicates_skipped=self.duplicates_skipped + other.duplicates_skipped,
            unsupported_skipped=self.unsupported_skipped + other.unsupported_skipped,
            failed=self.failed + other.failed,
            processing_jobs_enqueued=self.processing_jobs_enqueued
            + other.processing_jobs_enqueued,
        )


def _stats_to_result(stats: ScanStats) -> dict[str, int]:
    return {
        "files_seen": stats.files_seen,
        "supported_files_seen": stats.supported_files_seen,
        "assets_created": stats.created_assets,
        "duplicates_skipped": stats.duplicates_skipped,
        "unsupported_skipped": stats.unsupported_skipped,
        "failed": stats.failed,
        "processing_jobs_enqueued": stats.processing_jobs_enqueued,
    }


def iter_scannable_files(root: Path = MEDIA_ORIGINALS_DIR):
    for path in root.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if MEDIA_ORIGINALS_TMP_DIR in path.parents:
            continue
        yield path


def _chunked_paths(batch_size: int = SCAN_BATCH_SIZE):
    batch: list[Path] = []
    for path in iter_scannable_files():
        batch.append(path)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _inspect_media_for_scan(
    source_path: Path, mime_type: str
) -> tuple[int | None, int | None, str | None, str | None, float | None]:
    if is_supported_video_mime_type(mime_type):
        video_metadata = inspect_video(source_path)
        return (
            video_metadata.width,
            video_metadata.height,
            video_metadata.video_codec,
            video_metadata.audio_codec,
            video_metadata.duration_seconds,
        )

    width, height = validate_supported_media(source_path, mime_type)
    return width, height, None, None, None


async def _process_batch(batch: list[Path], job_id: UUID) -> ScanStats:
    stats = ScanStats()
    thumbnail_items: list[BatchProcessingItem] = []
    embedding_items: list[dict[str, str | None]] = []
    face_items: list[dict[str, str | None]] = []

    with Session(engine) as session:
        thumbnail_processor = ThumbnailBatchProcessor(session)
        for path in batch:
            stats = stats.add(ScanStats(files_seen=1))
            mime_type = guess_mime_type(path)
            if not is_supported_media_mime_type(mime_type):
                stats = stats.add(ScanStats(unsupported_skipped=1))
                continue
            stats = stats.add(ScanStats(supported_files_seen=1))

            try:
                file_hash = compute_sha256(path)
            except OSError:
                logger.exception("Failed to hash %s during library scan", path)
                NotificationService(session).create_notification(
                    level=NotificationLevel.WARNING,
                    category=NotificationCategory.SCAN,
                    title="Scan failed to process file",
                    message="The scanner could not hash a file and skipped it.",
                    details={"path": str(path)},
                    related_job_id=job_id,
                )
                stats = stats.add(ScanStats(failed=1))
                continue

            existing_asset = session.exec(
                select(Asset).where(Asset.file_hash == file_hash)
            ).first()
            if existing_asset is not None:
                stats = stats.add(ScanStats(duplicates_skipped=1))
                thumbnail_items.append(BatchProcessingItem(asset_id=existing_asset.id))
                embedding_items.append(
                    {"asset_id": str(existing_asset.id), "job_id": None}
                )
                if not is_supported_video_mime_type(existing_asset.mime_type):
                    face_items.append(
                        {"asset_id": str(existing_asset.id), "job_id": None}
                    )
                continue

            try:
                (
                    width,
                    height,
                    video_codec,
                    audio_codec,
                    duration_seconds,
                ) = _inspect_media_for_scan(path, mime_type)
            except ValueError:
                logger.warning(
                    "Skipping unsupported file discovered during scan: %s", path
                )
                stats = stats.add(ScanStats(unsupported_skipped=1))
                continue

            asset = Asset(
                file_hash=file_hash,
                master_path=source_path_to_master_path(path),
                mime_type=mime_type,
                width=width,
                height=height,
                has_large_preview=should_generate_large_preview(width, height),
                file_size_bytes=path.stat().st_size,
                video_codec=video_codec,
                audio_codec=audio_codec,
                duration_seconds=duration_seconds,
                preview_status=VIDEO_PREVIEW_STATUS_PENDING
                if is_supported_video_mime_type(mime_type)
                else None,
            )
            session.add(asset)
            try:
                session.commit()
                session.refresh(asset)
            except IntegrityError:
                session.rollback()
                stats = stats.add(ScanStats(duplicates_skipped=1))
                continue

            thumbnail_items.append(BatchProcessingItem(asset_id=asset.id))
            embedding_items.append({"asset_id": str(asset.id), "job_id": None})
            if not is_supported_video_mime_type(asset.mime_type):
                face_items.append({"asset_id": str(asset.id), "job_id": None})
            stats = stats.add(
                ScanStats(
                    created_assets=1,
                )
            )

        thumbnail_processor.process_batch(thumbnail_items)
        embedding_queued = False
        face_queued = False
        if embedding_items:
            embedding_queued = await enqueue_asset_embedding_batch_job(
                embedding_items,
                intent=INTENT_AI,
            )
        if face_items:
            face_queued = await enqueue_asset_faces_batch_job(
                face_items,
                auto_match=True,
                intent=INTENT_AI,
            )
        if embedding_items and not embedding_queued:
            stats = stats.add(ScanStats(failed=len(embedding_items)))
        if face_items and not face_queued:
            stats = stats.add(ScanStats(failed=len(face_items)))
        enqueued = (len(embedding_items) if embedding_queued else 0) + (
            len(face_items) if face_queued else 0
        )
        stats = stats.add(ScanStats(processing_jobs_enqueued=enqueued))

    return stats


def _mark_scan_running(job_id: UUID) -> None:
    with Session(engine) as session:
        JobService(session).mark_running(job_id, message="Scanning media library")
        NotificationService(session).create_notification(
            level=NotificationLevel.INFO,
            category=NotificationCategory.SCAN,
            title="Scan started",
            message="Library scan has started.",
            related_job_id=job_id,
        )


def _update_scan_progress(job_id: UUID, stats: ScanStats) -> None:
    with Session(engine) as session:
        JobService(session).update_progress(
            job_id,
            current=stats.files_seen,
            message=f"Scanned {stats.files_seen} files, created {stats.created_assets} assets",
        )


def _complete_scan(job_id: UUID, stats: ScanStats) -> None:
    result = _stats_to_result(stats)
    with Session(engine) as session:
        JobService(session).complete_job(
            job_id,
            result=result,
            message="Library scan completed",
        )
        NotificationService(session).create_notification(
            level=NotificationLevel.SUCCESS,
            category=NotificationCategory.SCAN,
            title="Scan completed",
            message="Library scan completed successfully.",
            related_job_id=job_id,
            details=result,
        )


def _fail_scan(job_id: UUID, error_message: str, stats: ScanStats) -> None:
    result = _stats_to_result(stats)
    with Session(engine) as session:
        JobService(session).fail_job(job_id, error_message, result=result)
        NotificationService(session).create_notification(
            level=NotificationLevel.ERROR,
            category=NotificationCategory.SCAN,
            title="Scan failed",
            message=error_message,
            related_job_id=job_id,
            details=result,
        )


async def scan_originals_library(_: dict[str, object], job_id: str) -> dict[str, int]:
    job_uuid = UUID(job_id)
    stats = ScanStats()
    _mark_scan_running(job_uuid)

    try:
        for batch in _chunked_paths():
            stats = stats.add(await _process_batch(batch, job_uuid))
            _update_scan_progress(job_uuid, stats)
    except Exception as exc:
        logger.exception("Library scan job %s failed", job_uuid)
        _fail_scan(job_uuid, str(exc), stats)
        raise

    _complete_scan(job_uuid, stats)
    logger.info(
        "Completed library scan job %s: files_seen=%s supported=%s created=%s duplicates=%s unsupported=%s failed=%s enqueued=%s",
        job_uuid,
        stats.files_seen,
        stats.supported_files_seen,
        stats.created_assets,
        stats.duplicates_skipped,
        stats.unsupported_skipped,
        stats.failed,
        stats.processing_jobs_enqueued,
    )
    return _stats_to_result(stats)
