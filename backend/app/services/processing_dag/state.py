from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.models import Asset
from app.services.asset_processing import (
    AssetProcessingRepository,
    PROCESSING_STATUS_COMPLETED,
    PROCESSING_STATUS_FAILED,
    PROCESSING_STATUS_QUEUED,
    PROCESSING_STATUS_RUNNING,
)
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.assets.media import (
    VIDEO_PREVIEW_STATUS_READY,
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    processed_asset_dir,
    processed_video_preview_path,
    should_generate_small_in_api,
)
from app.services.embeddings.repository import EmbeddingRepository
from app.services.faces.repository import FaceRepository

from .definition import (
    NODE_CLIP_EMBEDDING,
    NODE_FACE_MATCHING,
    NODE_FACE_PROCESSING,
    NODE_IMAGE_PREVIEW,
    NODE_METADATA_REFRESH,
    NODE_SMALL_THUMBNAIL,
    NODE_TINY_THUMBNAIL,
    NODE_VIDEO_PREVIEW,
    get_node_definition,
)

ACTIVE_JOB_STATUSES = {"queued", "running"}


@dataclass(frozen=True)
class ProcessingNodeState:
    task: str
    asset_id: UUID
    ai_model_id: int | None
    applicable: bool
    completed: bool
    stale: bool
    retryable: bool
    blocked_by_dependencies: bool
    active: bool
    missing: bool
    required: bool
    dependencies: tuple[str, ...]

    @property
    def needs_processing(self) -> bool:
        return (
            self.applicable
            and self.required
            and not self.active
            and not self.blocked_by_dependencies
            and (self.missing or self.stale or self.retryable or not self.completed)
        )


class AssetProcessingDagStateService:
    def __init__(
        self,
        session: Session,
        *,
        asset_processing_repository: AssetProcessingRepository | None = None,
        ai_model_repository: AIModelRepository | None = None,
        embedding_repository: EmbeddingRepository | None = None,
        face_repository: FaceRepository | None = None,
    ) -> None:
        self.session = session
        self.asset_processing_repository = (
            asset_processing_repository or AssetProcessingRepository(session)
        )
        self.ai_model_repository = ai_model_repository or AIModelRepository(session)
        self.embedding_repository = embedding_repository or EmbeddingRepository(session)
        self.face_repository = face_repository or FaceRepository(session)

    def get_asset(self, asset_id: UUID) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def evaluate(
        self,
        *,
        asset: Asset,
        task: str,
        force: bool = False,
        require_face_match: bool = False,
        _seen: frozenset[str] | None = None,
    ) -> ProcessingNodeState:
        if asset.deleted_at is not None:
            return ProcessingNodeState(
                task=task,
                asset_id=asset.id,
                ai_model_id=None,
                applicable=False,
                completed=False,
                stale=False,
                retryable=False,
                blocked_by_dependencies=False,
                active=False,
                missing=False,
                required=False,
                dependencies=(),
            )

        ai_model_id = self._resolve_model_id(task)
        dependencies = self._dependencies_for_asset(asset, task)
        blocked = False
        seen = (_seen or frozenset()) | {task}
        for dependency in dependencies:
            if dependency in seen:
                continue
            dependency_state = self.evaluate(
                asset=asset,
                task=dependency,
                force=False,
                require_face_match=require_face_match,
                _seen=seen,
            )
            if dependency_state.needs_processing or not dependency_state.completed:
                blocked = True

        applicable = self._is_applicable(asset, task)
        required = self._is_required(asset, task, require_face_match=require_face_match)
        state = self.asset_processing_repository.get_state(
            asset_id=asset.id,
            ai_model_id=ai_model_id,
            task=task,
        )
        active = bool(
            state.row is not None
            and state.row.status in {PROCESSING_STATUS_QUEUED, PROCESSING_STATUS_RUNNING}
            and state.last_job is not None
            and state.last_job.status in ACTIVE_JOB_STATUSES
        )
        retryable = bool(
            state.row is not None
            and (
                state.row.status == PROCESSING_STATUS_FAILED
                or (
                    state.row.status in {PROCESSING_STATUS_QUEUED, PROCESSING_STATUS_RUNNING}
                    and not active
                )
            )
        )
        completed, missing, stale = self._completion_state(
            asset=asset,
            task=task,
            ai_model_id=ai_model_id,
            require_face_match=require_face_match,
        )
        if force and applicable and required:
            completed = False
            stale = stale or True
        return ProcessingNodeState(
            task=task,
            asset_id=asset.id,
            ai_model_id=ai_model_id,
            applicable=applicable,
            completed=completed,
            stale=stale,
            retryable=retryable,
            blocked_by_dependencies=blocked,
            active=active,
            missing=missing,
            required=required,
            dependencies=dependencies,
        )

    def _resolve_model_id(self, task: str) -> int | None:
        try:
            if task == NODE_CLIP_EMBEDDING:
                return self.ai_model_repository.get_default_model_for_task(
                    AI_MODEL_TASK_CLIP_EMBEDDING
                ).id
            if task == NODE_FACE_PROCESSING:
                return self.ai_model_repository.get_default_model_for_task(
                    AI_MODEL_TASK_FACE_RECOGNITION
                ).id
        except AIModelConfigurationError:
            return None
        return None

    def _dependencies_for_asset(self, asset: Asset, task: str) -> tuple[str, ...]:
        definition = get_node_definition(task)
        dependencies = list(definition.base_dependencies)
        if task == NODE_CLIP_EMBEDDING and is_supported_video_mime_type(asset.mime_type):
            dependencies.append(NODE_SMALL_THUMBNAIL)
        return tuple(dict.fromkeys(dependencies))

    def _is_applicable(self, asset: Asset, task: str) -> bool:
        if task == NODE_IMAGE_PREVIEW:
            return is_supported_image_mime_type(asset.mime_type) and asset.has_large_preview
        if task == NODE_VIDEO_PREVIEW:
            return is_supported_video_mime_type(asset.mime_type)
        if task == NODE_FACE_PROCESSING:
            return is_supported_image_mime_type(asset.mime_type)
        if task == NODE_FACE_MATCHING:
            return is_supported_image_mime_type(asset.mime_type)
        if task in {NODE_TINY_THUMBNAIL, NODE_SMALL_THUMBNAIL, NODE_METADATA_REFRESH, NODE_CLIP_EMBEDDING}:
            return is_supported_image_mime_type(asset.mime_type) or is_supported_video_mime_type(asset.mime_type)
        return True

    def _is_required(
        self,
        asset: Asset,
        task: str,
        *,
        require_face_match: bool,
    ) -> bool:
        if task == NODE_SMALL_THUMBNAIL:
            return is_supported_video_mime_type(asset.mime_type) or should_generate_small_in_api(
                asset.mime_type,
                asset.file_size_bytes or 0,
            )
        if task == NODE_IMAGE_PREVIEW:
            return is_supported_image_mime_type(asset.mime_type) and asset.has_large_preview
        if task == NODE_VIDEO_PREVIEW:
            return is_supported_video_mime_type(asset.mime_type)
        if task == NODE_FACE_MATCHING:
            return require_face_match
        return self._is_applicable(asset, task)

    def _completion_state(
        self,
        *,
        asset: Asset,
        task: str,
        ai_model_id: int | None,
        require_face_match: bool,
    ) -> tuple[bool, bool, bool]:
        state = self.asset_processing_repository.get_state(
            asset_id=asset.id,
            ai_model_id=ai_model_id,
            task=task,
        )
        row_completed = bool(
            state.row is not None and state.row.status == PROCESSING_STATUS_COMPLETED
        )
        if task == NODE_METADATA_REFRESH:
            return row_completed, not row_completed, False
        if task == NODE_TINY_THUMBNAIL:
            path = processed_asset_dir(asset.id) / "tiny.webp"
            present = path.is_file()
            return present, not present, row_completed and not present
        if task == NODE_SMALL_THUMBNAIL:
            path = processed_asset_dir(asset.id) / "small.webp"
            if not self._is_required(asset, task, require_face_match=require_face_match):
                return True, False, False
            present = path.is_file()
            return present, not present, row_completed and not present
        if task == NODE_IMAGE_PREVIEW:
            if not self._is_required(asset, task, require_face_match=require_face_match):
                return True, False, False
            path = processed_asset_dir(asset.id) / "large.webp"
            present = path.is_file()
            return present, not present, row_completed and not present
        if task == NODE_VIDEO_PREVIEW:
            if not self._is_required(asset, task, require_face_match=require_face_match):
                return True, False, False
            path = processed_video_preview_path(asset.id)
            present = path.is_file()
            completed = present and asset.preview_status == VIDEO_PREVIEW_STATUS_READY
            stale = row_completed and not completed
            return completed, not completed, stale
        if task == NODE_CLIP_EMBEDDING:
            if ai_model_id is None:
                return True, False, False
            complete = self.embedding_repository.asset_has_embedding(asset, ai_model_id)
            stale = bool(asset.search_vector is not None and asset.search_model_id != ai_model_id)
            missing = not complete
            return complete, missing, stale
        if task == NODE_FACE_PROCESSING:
            if ai_model_id is None:
                return True, False, False
            complete = self.face_repository.asset_has_faces(
                asset_id=asset.id,
                model_id=ai_model_id,
            ) or row_completed
            missing = not complete
            stale = False
            return complete, missing, stale
        if task == NODE_FACE_MATCHING:
            if not require_face_match:
                return True, False, False
            return row_completed, not row_completed, False
        return False, True, False
