from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.database import engine
from app.models import Asset
from app.services.assets.hashing import compute_sha256
from app.services.assets.jobs import enqueue_asset_processing_job, enqueue_job
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

logger = logging.getLogger(__name__)
SCAN_BATCH_SIZE = 50
SCAN_JOB_NAME = "scan_originals_library"


@dataclass(frozen=True)
class ScanStats:
    scanned_files: int = 0
    unsupported_files: int = 0
    duplicate_files: int = 0
    created_assets: int = 0
    enqueued_jobs: int = 0

    def add(self, other: "ScanStats") -> "ScanStats":
        return ScanStats(
            scanned_files=self.scanned_files + other.scanned_files,
            unsupported_files=self.unsupported_files + other.unsupported_files,
            duplicate_files=self.duplicate_files + other.duplicate_files,
            created_assets=self.created_assets + other.created_assets,
            enqueued_jobs=self.enqueued_jobs + other.enqueued_jobs,
        )


async def enqueue_scan_job() -> bool:
    return await enqueue_job(SCAN_JOB_NAME)


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


async def _process_batch(batch: list[Path]) -> ScanStats:
    stats = ScanStats()

    with Session(engine) as session:
        for path in batch:
            stats = stats.add(ScanStats(scanned_files=1))
            mime_type = guess_mime_type(path)
            if not is_supported_media_mime_type(mime_type):
                stats = stats.add(ScanStats(unsupported_files=1))
                continue

            try:
                file_hash = compute_sha256(path)
            except OSError:
                logger.exception("Failed to hash %s during library scan", path)
                continue

            existing_asset = session.exec(
                select(Asset.id).where(Asset.file_hash == file_hash)
            ).first()
            if existing_asset is not None:
                stats = stats.add(ScanStats(duplicate_files=1))
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
                stats = stats.add(ScanStats(unsupported_files=1))
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
                stats = stats.add(ScanStats(duplicate_files=1))
                continue

            queued_job = await enqueue_asset_processing_job(asset.id)
            stats = stats.add(
                ScanStats(
                    created_assets=1,
                    enqueued_jobs=1 if queued_job else 0,
                )
            )

    return stats


async def scan_originals_library(_: dict[str, object]) -> dict[str, int]:
    logger.info("WORKER: STARTING SCAN")
    stats = ScanStats()
    for batch in _chunked_paths():
        logger.info("processing batch")
        stats = stats.add(await _process_batch(batch))

    logger.info(
        "Completed library scan: scanned=%s unsupported=%s duplicates=%s created=%s enqueued=%s",
        stats.scanned_files,
        stats.unsupported_files,
        stats.duplicate_files,
        stats.created_assets,
        stats.enqueued_jobs,
    )
    return {
        "scanned_files": stats.scanned_files,
        "unsupported_files": stats.unsupported_files,
        "duplicate_files": stats.duplicate_files,
        "created_assets": stats.created_assets,
        "enqueued_jobs": stats.enqueued_jobs,
    }
