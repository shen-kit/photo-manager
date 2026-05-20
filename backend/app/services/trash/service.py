from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.models import Asset
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.assets.media import (
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
    processed_video_preview_path,
)
from app.services.assets.repository import AssetRepository
from app.services.embeddings.repository import EmbeddingRepository
from app.services.face_assignment.service import (
    FaceAssignmentResult,
    FaceAssignmentService,
)
from app.services.faces.repository import FaceRepository
from app.services.jobs.queue import (
    enqueue_asset_embedding_job,
    enqueue_asset_faces_job,
    enqueue_asset_processing_job,
)
from app.services.people.maintenance import PeopleMaintenanceService
from app.services.trash.schemas import TrashSort


@dataclass(frozen=True)
class TrashRestoreJobResult:
    queued_metadata_job: bool
    queued_embedding_job: bool
    queued_face_job: bool
    ran_face_matching: bool
    matched_faces: int


@dataclass(frozen=True)
class TrashRestoreResult:
    asset: Asset
    tags: list[dict[str, object]] | None
    faces: list[dict[str, object]] | None
    jobs: TrashRestoreJobResult


class TrashService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.asset_repository = AssetRepository(session)
        self.face_repository = FaceRepository(session)
        self.embedding_repository = EmbeddingRepository(session)
        self.ai_model_repository = AIModelRepository(session)
        self.people_maintenance = PeopleMaintenanceService(session)

    def list_deleted_assets(
        self,
        *,
        page: int,
        page_size: int,
        sort: TrashSort,
    ) -> tuple[
        int,
        list[
            tuple[Asset, list[dict[str, object]] | None, list[dict[str, object]] | None]
        ],
    ]:
        total = self.asset_repository.count_deleted_assets()
        offset = (page - 1) * page_size
        rows = self.asset_repository.list_deleted_assets(
            limit=page_size,
            offset=offset,
            sort=sort,
        )
        return total, rows

    def get_deleted_asset_detail(
        self, asset_id: UUID
    ) -> tuple[Asset, list[dict[str, object]] | None, list[dict[str, object]] | None]:
        row = self.asset_repository.get_deleted_asset_detail(asset_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found in trash",
            )
        return row

    async def restore_asset(self, asset_id: UUID) -> TrashRestoreResult:
        asset = self.asset_repository.get_deleted_asset(asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found in trash",
            )

        source_path = self._require_restore_source(asset)
        restored_asset = self.asset_repository.restore_deleted_asset(asset)
        self.people_maintenance.reconcile_after_asset_restore(
            asset_id=restored_asset.id
        )

        jobs = await self._run_restore_follow_up(restored_asset, source_path)
        row = self.asset_repository.get_active_asset_detail(restored_asset.id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        hydrated_asset, tags, faces = row
        return TrashRestoreResult(
            asset=hydrated_asset,
            tags=tags,
            faces=faces,
            jobs=jobs,
        )

    async def restore_assets(
        self,
        asset_ids: list[UUID],
    ) -> tuple[list[TrashRestoreResult], list[tuple[UUID, str]]]:
        unique_asset_ids: list[UUID] = []
        seen: set[UUID] = set()
        for asset_id in asset_ids:
            if asset_id in seen:
                continue
            seen.add(asset_id)
            unique_asset_ids.append(asset_id)

        if not unique_asset_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="asset_ids must not be empty",
            )

        restored: list[TrashRestoreResult] = []
        failures: list[tuple[UUID, str]] = []
        for asset_id in unique_asset_ids:
            try:
                restored.append(await self.restore_asset(asset_id))
            except HTTPException as exc:
                failures.append((asset_id, str(exc.detail)))
        return restored, failures

    def _require_restore_source(self, asset: Asset) -> Path:
        try:
            source_path = master_path_to_source_path(asset.master_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted asset source path is invalid",
            ) from exc
        if not source_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deleted asset source file is missing",
            )
        return source_path

    async def _run_restore_follow_up(
        self,
        asset: Asset,
        source_path: Path,
    ) -> TrashRestoreJobResult:
        queued_metadata_job = False
        queued_embedding_job = False
        queued_face_job = False
        ran_face_matching = False
        matched_faces = 0

        if self._asset_needs_metadata_refresh(asset):
            queued_metadata_job = await enqueue_asset_processing_job(
                asset.id,
                enqueue_embedding=False,
                enqueue_faces=False,
            )

        if self._asset_needs_embedding(asset):
            queued_embedding_job = await enqueue_asset_embedding_job(asset.id)

        if is_supported_image_mime_type(asset.mime_type):
            if self._asset_has_current_face_model_faces(asset.id):
                assignment_result: FaceAssignmentResult = FaceAssignmentService(
                    self.session
                ).assign_faces_for_asset(asset.id)
                ran_face_matching = True
                matched_faces = assignment_result.faces_matched
            else:
                queued_face_job = await enqueue_asset_faces_job(
                    asset.id,
                    force=False,
                    auto_match=True,
                )

        del source_path
        return TrashRestoreJobResult(
            queued_metadata_job=queued_metadata_job,
            queued_embedding_job=queued_embedding_job,
            queued_face_job=queued_face_job,
            ran_face_matching=ran_face_matching,
            matched_faces=matched_faces,
        )

    def _asset_has_current_face_model_faces(self, asset_id: UUID) -> bool:
        try:
            face_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError:
            return False
        return self.face_repository.asset_has_faces(
            asset_id=asset_id, model_id=face_model.id
        )

    def _asset_needs_embedding(self, asset: Asset) -> bool:
        try:
            clip_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_CLIP_EMBEDDING
            )
        except AIModelConfigurationError:
            return False
        return not self.embedding_repository.asset_has_embedding(asset, clip_model.id)

    def _asset_needs_metadata_refresh(self, asset: Asset) -> bool:
        asset_dir = processed_asset_dir(asset.id)
        if not (asset_dir / "tiny.webp").is_file():
            return True
        if not (asset_dir / "small.webp").is_file():
            return True
        if asset.has_large_preview and not (asset_dir / "large.webp").is_file():
            return True
        if is_supported_video_mime_type(asset.mime_type):
            if not processed_video_preview_path(asset.id).is_file():
                return True
        return False


def get_trash_service(session: Session = Depends(get_session)) -> TrashService:
    return TrashService(session)
