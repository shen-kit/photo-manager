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
from sqlmodel import Session, select

from app.core.database import engine, get_session
from app.models import Asset
from app.services.assets_media import (
    MEDIA_ORIGINALS_DIR,
    build_fast_variants,
    should_generate_large_preview,
    should_generate_small_in_api,
    validate_supported_image,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)


@dataclass
class AssetProcessResult:
    asset: Asset
    queued_job: bool


def active_asset_where():
    return Asset.deleted_at.is_(None)


def guess_mime_type(path: Path, uploaded_content_type: str | None = None) -> str:
    if uploaded_content_type:
        return uploaded_content_type
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    detected = imghdr.what(path)
    return f"image/{detected}" if detected else "application/octet-stream"


def _coerce_relative_path(path: Path) -> str:
    normalized = Path(str(path)).as_posix().lstrip("/")
    if normalized.startswith("../") or normalized == "..":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File path must stay within the library root")
    return normalized


def _generate_fast_artifacts(asset_id: UUID, original_path: Path, include_small: bool) -> None:
    try:
        blurhash_value = build_fast_variants(original_path, asset_id, include_small=include_small)
    except Exception:
        logger.exception("Failed to generate fast asset variants for %s", asset_id)
        return

    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            return
        asset.blurhash = blurhash_value
        session.add(asset)
        session.commit()


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
        candidate = Path(file_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            try:
                relative_path = resolved.relative_to(MEDIA_ORIGINALS_DIR)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Absolute file paths must resolve within the originals library root",
                ) from exc
        else:
            relative_path = Path(file_path)
            resolved = (MEDIA_ORIGINALS_DIR / relative_path).resolve()

        try:
            resolved.relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolved file path escapes the library root") from exc

        if not resolved.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original file was not found")

        return _coerce_relative_path(relative_path), resolved

    async def process_new_asset(
        self,
        file_path: str,
        user_id: UUID,
        *,
        uploaded_content_type: str | None = None,
    ) -> AssetProcessResult:
        del user_id

        relative_path, source_path = self.resolve_original_path(file_path)
        file_hash = self._compute_sha256(source_path)
        existing_asset = self.session.exec(
            select(Asset).where(Asset.file_hash == file_hash, active_asset_where())
        ).first()
        if existing_asset is not None:
            self._cleanup_duplicate_upload(source_path, existing_asset.master_path)
            return AssetProcessResult(asset=existing_asset, queued_job=False)

        try:
            width, height = validate_supported_image(source_path)
        except ValueError as exc:
            self._cleanup_invalid_upload(source_path)
            logger.warning("Rejecting unsupported asset during ingest: %s", source_path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image file") from exc

        asset = Asset(
            file_hash=file_hash,
            master_path=relative_path,
            mime_type=guess_mime_type(source_path, uploaded_content_type),
            width=width,
            height=height,
            has_large_preview=should_generate_large_preview(width, height),
            file_size_bytes=source_path.stat().st_size,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        include_small = should_generate_small_in_api(asset.mime_type, asset.file_size_bytes or 0)
        if self.background_tasks is None:
            _generate_fast_artifacts(asset.id, source_path, include_small)
        else:
            self.background_tasks.add_task(_generate_fast_artifacts, asset.id, source_path, include_small)
        queued_job = await _enqueue_asset_job(asset.id)
        return AssetProcessResult(asset=asset, queued_job=queued_job)

    def _compute_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _cleanup_duplicate_upload(self, source_path: Path, existing_master_path: str) -> None:
        if not self._is_temp_upload(source_path):
            return
        existing_path = (MEDIA_ORIGINALS_DIR / existing_master_path).resolve()
        if source_path == existing_path:
            return
        source_path.unlink(missing_ok=True)

    def _cleanup_invalid_upload(self, source_path: Path) -> None:
        if self._is_temp_upload(source_path):
            source_path.unlink(missing_ok=True)

    def _is_temp_upload(self, source_path: Path) -> bool:
        try:
            relative = source_path.resolve().relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError:
            return False
        return relative.parts[:1] == ("uploads",)


def get_asset_service(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AssetService:
    return AssetService(session=session, background_tasks=background_tasks)
