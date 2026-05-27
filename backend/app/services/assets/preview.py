from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Asset, Job
from app.services.asset_processing.service import AssetProcessingTrackerService
from app.services.assets.media import (
    VIDEO_PREVIEW_STATUS_FAILED,
    VIDEO_PREVIEW_STATUS_PENDING,
    VIDEO_PREVIEW_STATUS_PROCESSING,
    VIDEO_PREVIEW_STATUS_READY,
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
    processed_video_preview_path,
    write_asset_variants,
    write_video_preview,
)
from app.services.assets.urls import build_preview_url
from app.services.jobs.dispatcher import (
    GENERATE_ASSET_PREVIEW_JOB_NAME,
    INTENT_INTERACTIVE,
    INTENT_PREVIEW,
    JobDispatcher,
    preview_dedup_key,
)
from app.services.jobs.service import JobService
from app.services.processing_dag import (
    AssetProcessingDagService,
    NODE_IMAGE_PREVIEW,
    NODE_VIDEO_PREVIEW,
)

logger = logging.getLogger(__name__)
PREVIEW_JOB_KEY = "generate_asset_preview"
IMAGE_PREVIEW_TASK = "image_preview"
VIDEO_PREVIEW_TASK = "video_preview"
SYNC_PREVIEW_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
SYNC_PREVIEW_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
PREVIEW_PRIORITY_VALUES = {"low", "normal", "high"}

PreviewEnsureStatus = Literal[
    "ready",
    "generating",
    "failed",
    "unsupported",
    "not_found",
]
PreviewPriority = Literal["low", "normal", "high"]


@dataclass(frozen=True)
class AssetPreviewEnsureItem:
    asset_id: UUID
    status: PreviewEnsureStatus
    preview_url: str | None
    job_id: UUID | None
    error: str | None


class AssetPreviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)
        self.tracker = AssetProcessingTrackerService(session)

    async def ensure_previews(
        self,
        *,
        asset_ids: list[UUID],
        base_url: str,
        priority: PreviewPriority = "low",
    ) -> list[AssetPreviewEnsureItem]:
        ordered_ids = _dedupe_asset_ids(asset_ids)
        assets = self._list_assets_by_ids(ordered_ids)
        results: list[AssetPreviewEnsureItem] = []
        for asset_id in ordered_ids:
            asset = assets.get(asset_id)
            if asset is None:
                results.append(
                    AssetPreviewEnsureItem(
                        asset_id=asset_id,
                        status="not_found",
                        preview_url=None,
                        job_id=None,
                        error="Asset not found or not accessible",
                    )
                )
                continue
            results.append(
                await self._ensure_single_preview(
                    asset=asset,
                    base_url=base_url,
                    priority=priority,
                )
            )
        return results

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

    async def _ensure_single_preview(
        self,
        *,
        asset: Asset,
        base_url: str,
        priority: PreviewPriority,
    ) -> AssetPreviewEnsureItem:
        if is_supported_video_mime_type(asset.mime_type):
            return await self._ensure_video_preview(
                asset=asset,
                base_url=base_url,
                priority=priority,
            )
        if is_supported_image_mime_type(asset.mime_type):
            return await self._ensure_image_preview(
                asset=asset,
                base_url=base_url,
                priority=priority,
            )
        return AssetPreviewEnsureItem(
            asset_id=asset.id,
            status="unsupported",
            preview_url=None,
            job_id=None,
            error="Unsupported asset type",
        )

    async def _ensure_image_preview(
        self,
        *,
        asset: Asset,
        base_url: str,
        priority: PreviewPriority,
    ) -> AssetPreviewEnsureItem:
        preview_url = build_preview_url(base_url, asset)
        if not asset.has_large_preview:
            return AssetPreviewEnsureItem(
                asset_id=asset.id,
                status="ready",
                preview_url=preview_url,
                job_id=None,
                error=None,
            )

        preview_path = processed_asset_dir(asset.id) / "large.webp"
        if preview_path.is_file():
            return self._ready_item(asset, base_url)

        if self._can_generate_image_preview_inline(asset):
            try:
                self.generate_image_preview(asset.id)
            except Exception as exc:
                logger.warning(
                    "Synchronous preview generation failed for asset %s: %s",
                    asset.id,
                    exc,
                )
                self.tracker.mark_failed(
                    asset_id=asset.id,
                    ai_model_id=None,
                    task=IMAGE_PREVIEW_TASK,
                    job_id=None,
                    error_message=str(exc),
                )
                return AssetPreviewEnsureItem(
                    asset_id=asset.id,
                    status="failed",
                    preview_url=None,
                    job_id=None,
                    error=str(exc),
                )
            self.tracker.mark_completed(
                asset_id=asset.id,
                ai_model_id=None,
                task=IMAGE_PREVIEW_TASK,
                job_id=None,
                output_count=1,
            )
            return self._ready_item(asset, base_url)

        job = await self._ensure_preview_job(asset=asset, priority=priority)
        if job is None:
            return AssetPreviewEnsureItem(
                asset_id=asset.id,
                status="failed",
                preview_url=None,
                job_id=None,
                error="Failed to queue preview generation",
            )
        return AssetPreviewEnsureItem(
            asset_id=asset.id,
            status="generating",
            preview_url=None,
            job_id=job.id,
            error=None,
        )

    async def _ensure_video_preview(
        self,
        *,
        asset: Asset,
        base_url: str,
        priority: PreviewPriority,
    ) -> AssetPreviewEnsureItem:
        preview_path = processed_video_preview_path(asset.id)
        if preview_path.is_file():
            if asset.preview_status != VIDEO_PREVIEW_STATUS_READY:
                asset.preview_status = VIDEO_PREVIEW_STATUS_READY
                self.session.add(asset)
                self.session.commit()
            return self._ready_item(asset, base_url)

        asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
        self.session.add(asset)
        self.session.commit()

        job = await self._ensure_preview_job(asset=asset, priority=priority)
        if job is None:
            return AssetPreviewEnsureItem(
                asset_id=asset.id,
                status="failed",
                preview_url=None,
                job_id=None,
                error="Failed to queue preview generation",
            )
        return AssetPreviewEnsureItem(
            asset_id=asset.id,
            status="generating",
            preview_url=None,
            job_id=job.id,
            error=None,
        )

    async def _ensure_preview_job(
        self,
        *,
        asset: Asset,
        priority: PreviewPriority,
    ) -> Job | None:
        task = (
            VIDEO_PREVIEW_TASK
            if is_supported_video_mime_type(asset.mime_type)
            else IMAGE_PREVIEW_TASK
        )
        dag_task = (
            NODE_VIDEO_PREVIEW
            if is_supported_video_mime_type(asset.mime_type)
            else NODE_IMAGE_PREVIEW
        )
        dag_state = AssetProcessingDagService(self.session).evaluate(
            asset=asset,
            task=dag_task,
        )
        if not dag_state.needs_processing:
            return None
        try:
            dispatch = await JobDispatcher(self.session).dispatch(
                job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
                args=[str(asset.id), None, priority],
                type=PREVIEW_JOB_KEY,
                parameters={"asset_id": str(asset.id), "priority": priority},
                job_key=PREVIEW_JOB_KEY,
                intent=INTENT_INTERACTIVE if priority == "high" else INTENT_PREVIEW,
                dedup_key=preview_dedup_key(asset.id),
                related_asset_id=asset.id,
                is_visible=False,
                force=False,
                allow_active_duplicate=priority == "high",
            )
            job = dispatch.job
        except HTTPException:
            self.tracker.mark_failed(
                asset_id=asset.id,
                ai_model_id=None,
                task=task,
                job_id=None,
                error_message="Failed to enqueue preview job",
            )
            return None
        self.tracker.mark_queued(
            asset_id=asset.id,
            ai_model_id=None,
            task=task,
            job_id=job.id,
        )
        return job

    def _ready_item(self, asset: Asset, base_url: str) -> AssetPreviewEnsureItem:
        return AssetPreviewEnsureItem(
            asset_id=asset.id,
            status="ready",
            preview_url=build_preview_url(base_url, asset),
            job_id=None,
            error=None,
        )

    def _list_assets_by_ids(self, asset_ids: list[UUID]) -> dict[UUID, Asset]:
        if not asset_ids:
            return {}
        rows = self.session.exec(select(Asset).where(Asset.id.in_(asset_ids))).all()
        return {asset.id: asset for asset in rows}

    def _get_asset(self, asset_id: UUID) -> Asset:
        asset = self.session.get(Asset, asset_id)
        if asset is None:
            raise RuntimeError(f"Asset {asset_id} not found")
        return asset

    def _can_generate_image_preview_inline(self, asset: Asset) -> bool:
        return (
            asset.mime_type in SYNC_PREVIEW_IMAGE_MIME_TYPES
            and asset.file_size_bytes is not None
            and asset.file_size_bytes <= SYNC_PREVIEW_MAX_FILE_SIZE_BYTES
        )

    @staticmethod
    def _source_path(asset: Asset) -> Path:
        source_path = master_path_to_source_path(asset.master_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source file missing for asset {asset.id}")
        return source_path


def normalize_preview_priority(priority: str) -> PreviewPriority:
    normalized = priority.strip().lower()
    if normalized not in PREVIEW_PRIORITY_VALUES:
        raise ValueError(
            f"priority must be one of {', '.join(sorted(PREVIEW_PRIORITY_VALUES))}"
        )
    return normalized  # type: ignore[return-value]


def _dedupe_asset_ids(asset_ids: list[UUID]) -> list[UUID]:
    ordered_ids: list[UUID] = []
    seen: set[UUID] = set()
    for asset_id in asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        ordered_ids.append(asset_id)
    return ordered_ids
