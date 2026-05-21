from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models import Asset
from app.services.asset_processing.service import AssetProcessingTrackerService
from app.services.assets.media import (
    VIDEO_PREVIEW_STATUS_FAILED,
    VIDEO_PREVIEW_STATUS_PENDING,
    VIDEO_PREVIEW_STATUS_PROCESSING,
    VIDEO_PREVIEW_STATUS_READY,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
    processed_video_preview_path,
    write_asset_variants,
    write_video_preview,
)
from app.services.jobs.queue import enqueue_asset_preview_job
from app.services.jobs.service import JobService

logger = logging.getLogger(__name__)
PREVIEW_JOB_KEY = "generate_asset_preview"
IMAGE_PREVIEW_TASK = "image_preview"
VIDEO_PREVIEW_TASK = "video_preview"


@dataclass(frozen=True)
class AssetPreviewResolution:
    file_path: Path | None
    queued: bool


class AssetPreviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)
        self.tracker = AssetProcessingTrackerService(session)

    async def resolve_preview(self, asset_id: UUID) -> AssetPreviewResolution:
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        if is_supported_video_mime_type(asset.mime_type):
            return await self._resolve_video_preview(asset)
        return await self._resolve_image_preview(asset)

    def generate_image_preview(self, asset_id: UUID) -> Path:
        asset = self._get_asset(asset_id)
        source_path = self._source_path(asset)
        if not asset.has_large_preview:
            return source_path
        preview_path = processed_asset_dir(asset.id) / "large.webp"
        if not preview_path.is_file():
            write_asset_variants(source_path, asset.id, ("large",), asset.mime_type)
        return preview_path

    def generate_video_preview(self, asset_id: UUID) -> Path:
        asset = self._get_asset(asset_id)
        source_path = self._source_path(asset)
        preview_path = processed_video_preview_path(asset.id)
        asset.preview_status = VIDEO_PREVIEW_STATUS_PROCESSING
        self.session.add(asset)
        self.session.commit()
        try:
            if not preview_path.is_file():
                write_video_preview(source_path, asset.id)
        except Exception:
            asset.preview_status = VIDEO_PREVIEW_STATUS_FAILED
            self.session.add(asset)
            self.session.commit()
            logger.exception("Failed to generate video preview for asset %s", asset.id)
            raise
        asset.preview_status = VIDEO_PREVIEW_STATUS_READY
        self.session.add(asset)
        self.session.commit()
        return preview_path

    async def _resolve_image_preview(self, asset: Asset) -> AssetPreviewResolution:
        if not asset.has_large_preview:
            return AssetPreviewResolution(
                file_path=self._source_path(asset), queued=False
            )
        preview_path = processed_asset_dir(asset.id) / "large.webp"
        if preview_path.is_file():
            return AssetPreviewResolution(file_path=preview_path, queued=False)
        if await self._ensure_preview_job(asset.id):
            return AssetPreviewResolution(file_path=None, queued=True)
        return AssetPreviewResolution(file_path=None, queued=False)

    async def _resolve_video_preview(self, asset: Asset) -> AssetPreviewResolution:
        preview_path = processed_video_preview_path(asset.id)
        if preview_path.is_file():
            if asset.preview_status != VIDEO_PREVIEW_STATUS_READY:
                asset.preview_status = VIDEO_PREVIEW_STATUS_READY
                self.session.add(asset)
                self.session.commit()
            return AssetPreviewResolution(file_path=preview_path, queued=False)
        asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
        self.session.add(asset)
        self.session.commit()
        if await self._ensure_preview_job(asset.id):
            return AssetPreviewResolution(file_path=None, queued=True)
        return AssetPreviewResolution(file_path=None, queued=False)

    async def _ensure_preview_job(self, asset_id: UUID) -> bool:
        asset = self._get_asset(asset_id)
        task = (
            VIDEO_PREVIEW_TASK
            if is_supported_video_mime_type(asset.mime_type)
            else IMAGE_PREVIEW_TASK
        )
        active_job = self.job_service.find_active_job_for_asset(
            job_key=PREVIEW_JOB_KEY,
            related_asset_id=asset_id,
        )
        if active_job is not None:
            return False
        job = self.job_service.create_job(
            PREVIEW_JOB_KEY,
            parameters={"asset_id": str(asset_id)},
            job_key=PREVIEW_JOB_KEY,
            related_asset_id=asset_id,
            is_visible=False,
        )
        queued = await enqueue_asset_preview_job(asset_id, job_id=job.id)
        if not queued:
            self.job_service.fail_job(job.id, "Failed to enqueue preview job")
            self.tracker.mark_failed(
                asset_id=asset_id,
                ai_model_id=None,
                task=task,
                job_id=job.id,
                error_message="Failed to enqueue preview job",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to queue preview generation",
            )
        self.tracker.mark_queued(
            asset_id=asset_id,
            ai_model_id=None,
            task=task,
            job_id=job.id,
        )
        return True

    def _get_asset(self, asset_id: UUID) -> Asset:
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            raise RuntimeError(f"Asset {asset_id} not found")
        return asset

    @staticmethod
    def _source_path(asset: Asset) -> Path:
        source_path = master_path_to_source_path(asset.master_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source file missing for asset {asset.id}")
        return source_path
