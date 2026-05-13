from __future__ import annotations

import hashlib
import imghdr
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from arq.connections import RedisSettings, create_pool
from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.database import engine, get_session
from app.models import Asset
from app.services.assets_media import (
    MediaInspection,
    build_fast_variants,
    canonical_original_path,
    inspect_video,
    is_canonical_hashed_original,
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_video_preview_path,
    resolve_source_input,
    should_generate_large_preview,
    should_generate_small_in_api,
    source_path_to_master_path,
    validate_supported_media,
    VIDEO_PREVIEW_STATUS_PENDING,
    VIDEO_PREVIEW_STATUS_READY,
    is_temporary_original_path,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)


@dataclass
class AssetProcessResult:
    asset: Asset
    queued_job: bool
    created_new: bool


def active_asset_where():
    return Asset.deleted_at.is_(None)


def guess_mime_type(path: Path, uploaded_content_type: str | None = None) -> str:
    if uploaded_content_type and uploaded_content_type != "application/octet-stream":
        return uploaded_content_type
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    detected = imghdr.what(path)
    return f"image/{detected}" if detected else "application/octet-stream"


def _generate_fast_artifacts(asset_id: UUID, original_path: Path, include_small: bool) -> None:
    try:
        with Session(engine) as session:
            asset = session.get(Asset, asset_id)
            if asset is None:
                return
            blurhash_value = build_fast_variants(
                original_path,
                asset_id,
                include_small=include_small,
                mime_type=asset.mime_type,
            )
            asset.blurhash = blurhash_value
            session.add(asset)
            session.commit()
    except Exception:
        logger.exception("Failed to generate fast asset variants for %s", asset_id)
        return


async def _enqueue_asset_job(asset_id: UUID) -> bool:
    try:
        redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        try:
            await redis.enqueue_job("process_asset_metadata", str(asset_id))
        finally:
            await redis.aclose()
    except Exception:
        logger.exception("Failed to enqueue heavy asset processing for %s", asset_id)
        return False
    return True


class AssetService:
    def __init__(self, session: Session, background_tasks: BackgroundTasks | None = None) -> None:
        self.session = session
        self.background_tasks = background_tasks

    def resolve_original_path(self, file_path: str) -> tuple[str, Path]:
        try:
            return resolve_source_input(file_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original file was not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async def process_new_asset(
        self,
        file_path: str,
        user_id: UUID,
        *,
        uploaded_content_type: str | None = None,
        precomputed_file_hash: str | None = None,
        restore_deleted: bool = False,
    ) -> AssetProcessResult:
        del user_id

        relative_path, source_path = self.resolve_original_path(file_path)
        mime_type = guess_mime_type(source_path, uploaded_content_type)
        file_hash = precomputed_file_hash or self._compute_sha256(source_path)
        existing_asset = self.session.exec(select(Asset).where(Asset.file_hash == file_hash)).first()
        if existing_asset is not None:
            if existing_asset.deleted_at is not None and restore_deleted:
                width, height, video_metadata = self._inspect_media_or_raise(source_path, mime_type)
                relative_path, source_path = self._ensure_canonical_original_location(source_path, file_hash)
                return await self._restore_deleted_asset(
                    asset=existing_asset,
                    source_path=source_path,
                    master_path=relative_path,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    video_metadata=video_metadata,
                )
            queued_job = False
            if self._asset_requires_reprocessing(existing_asset):
                existing_asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
                self.session.add(existing_asset)
                self.session.commit()
                self.session.refresh(existing_asset)
                queued_job = await _enqueue_asset_job(existing_asset.id)
            self._cleanup_duplicate_source(source_path, existing_asset.master_path)
            return AssetProcessResult(asset=existing_asset, queued_job=queued_job, created_new=False)

        width, height, video_metadata = self._inspect_media_or_raise(source_path, mime_type)
        relative_path, source_path = self._ensure_canonical_original_location(source_path, file_hash)

        asset = Asset(
            file_hash=file_hash,
            master_path=relative_path,
            mime_type=mime_type,
            width=width,
            height=height,
            has_large_preview=should_generate_large_preview(width, height),
            file_size_bytes=source_path.stat().st_size,
            video_codec=video_metadata.video_codec if video_metadata else None,
            audio_codec=video_metadata.audio_codec if video_metadata else None,
            duration_seconds=video_metadata.duration_seconds if video_metadata else None,
            preview_status=VIDEO_PREVIEW_STATUS_PENDING if video_metadata else None,
        )
        self.session.add(asset)
        try:
            self.session.commit()
            self.session.refresh(asset)
        except IntegrityError:
            self.session.rollback()
            existing_asset = self.session.exec(select(Asset).where(Asset.file_hash == file_hash)).first()
            if existing_asset is None:
                raise
            if existing_asset.deleted_at is not None and restore_deleted:
                width, height, video_metadata = self._inspect_media_or_raise(source_path, mime_type)
                relative_path, source_path = self._ensure_canonical_original_location(source_path, file_hash)
                return await self._restore_deleted_asset(
                    asset=existing_asset,
                    source_path=source_path,
                    master_path=relative_path,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    video_metadata=video_metadata,
                )
            queued_job = False
            if self._asset_requires_reprocessing(existing_asset):
                existing_asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
                self.session.add(existing_asset)
                self.session.commit()
                self.session.refresh(existing_asset)
                queued_job = await _enqueue_asset_job(existing_asset.id)
            self._cleanup_duplicate_source(source_path, existing_asset.master_path)
            return AssetProcessResult(asset=existing_asset, queued_job=queued_job, created_new=False)

        include_small = is_supported_video_mime_type(asset.mime_type) or should_generate_small_in_api(
            asset.mime_type,
            asset.file_size_bytes or 0,
        )
        if is_supported_image_mime_type(asset.mime_type) or is_supported_video_mime_type(asset.mime_type):
            if self.background_tasks is None:
                _generate_fast_artifacts(asset.id, source_path, include_small)
            else:
                self.background_tasks.add_task(_generate_fast_artifacts, asset.id, source_path, include_small)
        queued_job = await _enqueue_asset_job(asset.id)
        return AssetProcessResult(asset=asset, queued_job=queued_job, created_new=True)

    def _compute_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _asset_requires_reprocessing(self, asset: Asset) -> bool:
        if not is_supported_video_mime_type(asset.mime_type):
            return False
        if asset.preview_status != VIDEO_PREVIEW_STATUS_READY:
            return True
        if asset.video_codec is None or asset.duration_seconds is None:
            return True
        return not processed_video_preview_path(asset.id).is_file()

    def _inspect_media_or_raise(self, source_path: Path, mime_type: str) -> tuple[int | None, int | None, MediaInspection | None]:
        try:
            if is_supported_video_mime_type(mime_type):
                video_metadata = inspect_video(source_path)
                return video_metadata.width, video_metadata.height, video_metadata
            width, height = validate_supported_media(source_path, mime_type)
            return width, height, None
        except ValueError as exc:
            self._cleanup_temporary_source(source_path)
            logger.warning("Rejecting unsupported asset: %s", source_path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exc)}\nAsset path: {source_path}") from exc

    def _cleanup_temporary_source(self, source_path: Path) -> None:
        if is_temporary_original_path(source_path):
            source_path.unlink(missing_ok=True)

    def _cleanup_duplicate_source(self, source_path: Path, existing_master_path: str) -> None:
        self._cleanup_temporary_source(source_path)

        try:
            existing_source_path = master_path_to_source_path(existing_master_path)
        except ValueError:
            return

        try:
            source_master_path = source_path_to_master_path(source_path)
        except ValueError:
            return

        if source_path == existing_source_path or source_master_path == existing_master_path:
            return
        source_path.unlink(missing_ok=True)

    def _ensure_canonical_original_location(self, source_path: Path, file_hash: str) -> tuple[str, Path]:
        if is_canonical_hashed_original(source_path, file_hash):
            return source_path_to_master_path(source_path), source_path

        destination = canonical_original_path(file_hash, source_path.suffix)
        if destination == source_path:
            return source_path_to_master_path(source_path), source_path

        if destination.exists():
            self._cleanup_temporary_source(source_path)
            return source_path_to_master_path(destination), destination

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            _ = source_path.rename(destination)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=exc.strerror,
            ) from exc
        return source_path_to_master_path(destination), destination

    async def _restore_deleted_asset(
        self,
        *,
        asset: Asset,
        source_path: Path,
        master_path: str,
        mime_type: str,
        width: int | None,
        height: int | None,
        video_metadata: MediaInspection | None,
    ) -> AssetProcessResult:
        asset.master_path = master_path
        asset.mime_type = mime_type
        asset.width = width
        asset.height = height
        asset.has_large_preview = should_generate_large_preview(width, height)
        asset.file_size_bytes = source_path.stat().st_size
        asset.video_codec = video_metadata.video_codec if video_metadata else None
        asset.audio_codec = video_metadata.audio_codec if video_metadata else None
        asset.duration_seconds = video_metadata.duration_seconds if video_metadata else None
        asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING if video_metadata else None
        asset.deleted_at = None
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        include_small = is_supported_video_mime_type(asset.mime_type) or should_generate_small_in_api(
            asset.mime_type,
            asset.file_size_bytes or 0,
        )
        if is_supported_image_mime_type(asset.mime_type) or is_supported_video_mime_type(asset.mime_type):
            if self.background_tasks is None:
                _generate_fast_artifacts(asset.id, source_path, include_small)
            else:
                self.background_tasks.add_task(_generate_fast_artifacts, asset.id, source_path, include_small)
        queued_job = await _enqueue_asset_job(asset.id)
        return AssetProcessResult(asset=asset, queued_job=queued_job, created_new=False)


def get_asset_service(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AssetService:
    return AssetService(session=session, background_tasks=background_tasks)
