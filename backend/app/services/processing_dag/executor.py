from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.models import Asset
from app.services.asset_processing import AssetProcessingTrackerService
from app.services.assets.media import is_supported_image_mime_type
from app.services.assets.media import is_supported_video_mime_type
from app.services.face_assignment.service import FaceAssignmentService
from app.services.jobs.dispatcher import INTENT_INTERACTIVE
from app.services.jobs.queue import (
    enqueue_asset_embedding_job,
    enqueue_asset_faces_job,
    enqueue_asset_processing_job,
    enqueue_asset_preview_job,
)

from .definition import (
    NODE_CLIP_EMBEDDING,
    NODE_FACE_MATCHING,
    NODE_FACE_PROCESSING,
    NODE_IMAGE_PREVIEW,
    NODE_METADATA_REFRESH,
    NODE_SMALL_THUMBNAIL,
    NODE_TINY_THUMBNAIL,
    NODE_VIDEO_PREVIEW,
)
from .policies import ProcessingPolicy, PREVIEW_POLICY, RESTORE_POLICY
from .state import AssetProcessingDagStateService, ProcessingNodeState


@dataclass(frozen=True)
class ProcessingFollowUpResult:
    queued_metadata_job: bool = False
    queued_embedding_job: bool = False
    queued_face_job: bool = False
    queued_preview_job: bool = False
    ran_face_matching: bool = False
    matched_faces: int = 0


@dataclass(frozen=True)
class ScanDagPlan:
    require_tiny_thumbnail: bool
    require_small_thumbnail: bool
    queue_clip: bool
    queue_faces: bool


class AssetProcessingDagService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.state = AssetProcessingDagStateService(session)
        self.tracker = AssetProcessingTrackerService(session)

    def evaluate(
        self,
        *,
        asset: Asset,
        task: str,
        force: bool = False,
        require_face_match: bool = False,
    ) -> ProcessingNodeState:
        return self.state.evaluate(
            asset=asset,
            task=task,
            force=force,
            require_face_match=require_face_match,
        )

    async def schedule_asset_created(
        self,
        asset_id: UUID,
        *,
        parent_job_id: UUID | None = None,
    ) -> bool:
        asset = self._require_asset(asset_id)
        node = self.evaluate(asset=asset, task=NODE_METADATA_REFRESH)
        if not node.needs_processing:
            return False
        return await enqueue_asset_processing_job(
            asset.id,
            parent_job_id=parent_job_id,
        )

    async def schedule_metadata_follow_up(
        self,
        asset_id: UUID,
        *,
        enqueue_embedding: bool,
        enqueue_faces: bool,
        policy: ProcessingPolicy,
    ) -> ProcessingFollowUpResult:
        asset = self._require_asset(asset_id)
        queued_embedding_job = False
        queued_face_job = False
        if enqueue_embedding:
            clip_state = self.evaluate(asset=asset, task=NODE_CLIP_EMBEDDING)
            if clip_state.needs_processing:
                queued_embedding_job = await enqueue_asset_embedding_job(
                    asset.id,
                    force=policy.force,
                    intent=policy.intent,
                )
        if enqueue_faces and is_supported_image_mime_type(asset.mime_type):
            face_state = self.evaluate(
                asset=asset,
                task=NODE_FACE_PROCESSING,
                force=policy.force,
                require_face_match=policy.auto_match,
            )
            if face_state.needs_processing:
                queued_face_job = await enqueue_asset_faces_job(
                    asset.id,
                    force=policy.force,
                    auto_match=policy.auto_match,
                    intent=policy.intent,
                )
        return ProcessingFollowUpResult(
            queued_embedding_job=queued_embedding_job,
            queued_face_job=queued_face_job,
        )

    async def schedule_preview_node(
        self,
        asset: Asset,
        *,
        priority: str,
    ) -> bool:
        task = (
            NODE_VIDEO_PREVIEW
            if is_supported_video_mime_type(asset.mime_type)
            else NODE_IMAGE_PREVIEW
        )
        preview_policy = ProcessingPolicy(
            **{
                **PREVIEW_POLICY.__dict__,
                "intent": INTENT_INTERACTIVE
                if priority == "high"
                else PREVIEW_POLICY.intent,
                "priority": priority,
            }
        )
        state = self.evaluate(asset=asset, task=task)
        if not state.needs_processing:
            return False
        return await enqueue_asset_preview_job(
            asset.id,
            priority=preview_policy.priority,
            intent=preview_policy.intent,
        )

    async def schedule_clip_entrypoint(
        self,
        asset_id: UUID,
        *,
        force: bool,
        policy: ProcessingPolicy,
        job_id: UUID | None = None,
    ) -> bool:
        asset = self._require_asset(asset_id)
        node = self.evaluate(asset=asset, task=NODE_CLIP_EMBEDDING, force=force)
        if not force and not node.needs_processing:
            return False
        return await enqueue_asset_embedding_job(
            asset.id,
            force=force,
            job_id=job_id,
            intent=policy.intent,
        )

    async def schedule_face_entrypoint(
        self,
        asset_id: UUID,
        *,
        force: bool,
        auto_match: bool,
        policy: ProcessingPolicy,
        job_id: UUID | None = None,
    ) -> bool:
        asset = self._require_asset(asset_id)
        node = self.evaluate(
            asset=asset,
            task=NODE_FACE_PROCESSING,
            force=force,
            require_face_match=auto_match,
        )
        if not force and not node.needs_processing:
            return False
        return await enqueue_asset_faces_job(
            asset.id,
            force=force,
            auto_match=auto_match,
            job_id=job_id,
            intent=policy.intent,
        )

    async def schedule_restore_follow_up(self, asset_id: UUID) -> ProcessingFollowUpResult:
        asset = self._require_asset(asset_id)
        metadata_needed = any(
            self.evaluate(asset=asset, task=task).needs_processing
            for task in (NODE_TINY_THUMBNAIL, NODE_SMALL_THUMBNAIL)
        )
        queued_metadata_job = False
        if metadata_needed:
            queued_metadata_job = await enqueue_asset_processing_job(
                asset.id,
                enqueue_embedding=False,
                enqueue_faces=False,
            )

        follow_up = await self.schedule_metadata_follow_up(
            asset.id,
            enqueue_embedding=RESTORE_POLICY.enqueue_embedding,
            enqueue_faces=False,
            policy=RESTORE_POLICY,
        )
        ran_face_matching = False
        matched_faces = 0
        queued_face_job = False
        if is_supported_image_mime_type(asset.mime_type):
            face_state = self.evaluate(
                asset=asset,
                task=NODE_FACE_PROCESSING,
                require_face_match=True,
            )
            if face_state.completed:
                assignment_result = FaceAssignmentService(self.session).assign_faces_for_asset(
                    asset.id
                )
                self.tracker.mark_completed(
                    asset_id=asset.id,
                    ai_model_id=None,
                    task=NODE_FACE_MATCHING,
                    job_id=None,
                    output_count=assignment_result.faces_matched,
                )
                ran_face_matching = True
                matched_faces = assignment_result.faces_matched
            elif face_state.needs_processing:
                queued_face_job = await enqueue_asset_faces_job(
                    asset.id,
                    force=False,
                    auto_match=True,
                    intent=RESTORE_POLICY.intent,
                )
        return ProcessingFollowUpResult(
            queued_metadata_job=queued_metadata_job,
            queued_embedding_job=follow_up.queued_embedding_job,
            queued_face_job=queued_face_job,
            ran_face_matching=ran_face_matching,
            matched_faces=matched_faces,
        )

    def plan_scan_asset(self, asset_id: UUID) -> ScanDagPlan:
        asset = self._require_asset(asset_id)
        tiny = self.evaluate(asset=asset, task=NODE_TINY_THUMBNAIL)
        small = self.evaluate(asset=asset, task=NODE_SMALL_THUMBNAIL)
        clip = self.evaluate(asset=asset, task=NODE_CLIP_EMBEDDING)
        faces = self.evaluate(asset=asset, task=NODE_FACE_PROCESSING)
        return ScanDagPlan(
            require_tiny_thumbnail=tiny.needs_processing,
            require_small_thumbnail=small.needs_processing,
            queue_clip=clip.needs_processing,
            queue_faces=faces.needs_processing,
        )

    def repair_derivative_nodes(self, asset_id: UUID) -> bool:
        asset = self._require_asset(asset_id)
        checks = [
            self.evaluate(asset=asset, task=NODE_TINY_THUMBNAIL),
            self.evaluate(asset=asset, task=NODE_SMALL_THUMBNAIL),
            self.evaluate(asset=asset, task=NODE_IMAGE_PREVIEW),
            self.evaluate(asset=asset, task=NODE_VIDEO_PREVIEW),
        ]
        return any(check.needs_processing for check in checks)

    def mark_metadata_refresh_completed(
        self,
        *,
        asset: Asset,
        job_id: UUID | None,
    ) -> None:
        self.tracker.mark_completed(
            asset_id=asset.id,
            ai_model_id=None,
            task=NODE_METADATA_REFRESH,
            job_id=job_id,
            output_count=1,
        )

    def mark_thumbnail_nodes_completed(
        self,
        *,
        asset: Asset,
        job_id: UUID | None,
    ) -> None:
        tiny_state = self.evaluate(asset=asset, task=NODE_TINY_THUMBNAIL)
        if tiny_state.completed:
            self.tracker.mark_completed(
                asset_id=asset.id,
                ai_model_id=None,
                task=NODE_TINY_THUMBNAIL,
                job_id=job_id,
                output_count=1,
            )
        small_state = self.evaluate(asset=asset, task=NODE_SMALL_THUMBNAIL)
        if small_state.completed:
            self.tracker.mark_completed(
                asset_id=asset.id,
                ai_model_id=None,
                task=NODE_SMALL_THUMBNAIL,
                job_id=job_id,
                output_count=1,
            )

    def mark_face_matching_completed(
        self,
        *,
        asset_id: UUID,
        output_count: int,
        job_id: UUID | None,
    ) -> None:
        self.tracker.mark_completed(
            asset_id=asset_id,
            ai_model_id=None,
            task=NODE_FACE_MATCHING,
            job_id=job_id,
            output_count=output_count,
        )

    def _require_asset(self, asset_id: UUID) -> Asset:
        asset = self.state.get_asset(asset_id)
        if asset is None:  # pragma: no cover - service guard
            raise RuntimeError(f"Asset {asset_id} not found")
        return asset
