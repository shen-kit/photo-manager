from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules.setdefault("open_clip", MagicMock())
sys.modules.setdefault("torch", MagicMock())

from fastapi import HTTPException

from app.models import AIModel, Asset
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
)
from app.services.face_assignment.service import FaceAssignmentResult
from app.services.trash.service import TrashService


class _FakeAssetRepository:
    def __init__(self, asset: Asset | None) -> None:
        self.asset = asset
        self.restored_ids: list[str] = []

    def get_deleted_asset(self, asset_id):
        if (
            self.asset is not None
            and self.asset.id == asset_id
            and self.asset.deleted_at is not None
        ):
            return self.asset
        return None

    def restore_deleted_asset(self, asset):
        asset.deleted_at = None
        self.restored_ids.append(str(asset.id))
        self.asset = asset
        return asset

    def get_active_asset_detail(self, asset_id):
        if (
            self.asset is None
            or self.asset.id != asset_id
            or self.asset.deleted_at is not None
        ):
            return None
        return (self.asset, [], [])


class _FakePeopleMaintenance:
    def __init__(self) -> None:
        self.restore_calls: list[str] = []

    def reconcile_after_asset_restore(self, *, asset_id):
        self.restore_calls.append(str(asset_id))


class _FakeFaceRepository:
    def __init__(self, *, has_current_faces: bool) -> None:
        self.has_current_faces = has_current_faces
        self.calls: list[tuple[str, int]] = []

    def asset_has_faces(self, *, asset_id, model_id):
        self.calls.append((str(asset_id), model_id))
        return self.has_current_faces


class _FakeEmbeddingRepository:
    def __init__(self, *, has_current_embedding: bool) -> None:
        self.has_current_embedding = has_current_embedding
        self.calls: list[tuple[str, int]] = []

    def asset_has_embedding(self, asset, model_id):
        self.calls.append((str(asset.id), model_id))
        return self.has_current_embedding


class _FakeAIModelRepository:
    def __init__(self, *, clip_model_id: int = 11, face_model_id: int = 17) -> None:
        self.clip_model = AIModel(
            id=clip_model_id,
            task=AI_MODEL_TASK_CLIP_EMBEDDING,
            model_name="clip",
            version_tag="1",
            vector_dimensions=512,
            is_deprecated=False,
        )
        self.face_model = AIModel(
            id=face_model_id,
            task=AI_MODEL_TASK_FACE_RECOGNITION,
            model_name="buffalo",
            version_tag="1",
            vector_dimensions=512,
            is_deprecated=False,
        )

    def get_default_model_for_task(self, task: str):
        if task == AI_MODEL_TASK_CLIP_EMBEDDING:
            return self.clip_model
        if task == AI_MODEL_TASK_FACE_RECOGNITION:
            return self.face_model
        raise AssertionError(task)


class TrashServiceTest(unittest.TestCase):
    def _asset(self, *, deleted: bool = True) -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2024/test.jpg",
            mime_type="image/jpeg",
            width=1200,
            height=800,
            has_large_preview=True,
            created_at=datetime.now(timezone.utc),
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )

    def test_restore_asset_clears_deleted_at_and_runs_matching_for_existing_faces(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "photo.jpg"
            source_path.write_bytes(b"stub")
            asset = self._asset(deleted=True)
            service = TrashService(session=None)
            service.asset_repository = _FakeAssetRepository(asset)
            service.people_maintenance = _FakePeopleMaintenance()
            service.face_repository = _FakeFaceRepository(has_current_faces=True)
            service.embedding_repository = _FakeEmbeddingRepository(
                has_current_embedding=False
            )
            service.ai_model_repository = _FakeAIModelRepository()

            with (
                patch(
                    "app.services.trash.service.master_path_to_source_path",
                    return_value=source_path,
                ),
                patch(
                    "app.services.trash.service.FaceAssignmentService.assign_faces_for_asset",
                    return_value=FaceAssignmentResult(
                        asset_id=asset.id,
                        faces_seen=2,
                        faces_matched=1,
                        faces_unmatched=1,
                        assignments=[],
                    ),
                ) as match_mock,
                patch(
                    "app.services.trash.service.enqueue_asset_embedding_job",
                    new=AsyncMock(return_value=True),
                ) as embedding_mock,
                patch(
                    "app.services.trash.service.enqueue_asset_faces_job",
                    new=AsyncMock(return_value=True),
                ) as face_job_mock,
                patch(
                    "app.services.trash.service.enqueue_asset_processing_job",
                    new=AsyncMock(return_value=False),
                ) as metadata_mock,
            ):
                result = asyncio.run(service.restore_asset(asset.id))

        self.assertIsNone(result.asset.deleted_at)
        self.assertEqual(service.asset_repository.restored_ids, [str(asset.id)])
        self.assertEqual(
            service.people_maintenance.restore_calls,
            [str(asset.id)],
        )
        match_mock.assert_called_once_with(asset.id)
        embedding_mock.assert_awaited_once_with(asset.id)
        face_job_mock.assert_not_awaited()
        metadata_mock.assert_awaited_once()
        self.assertTrue(result.jobs.ran_face_matching)
        self.assertEqual(result.jobs.matched_faces, 1)
        self.assertTrue(result.jobs.queued_embedding_job)

    def test_restore_asset_enqueues_face_processing_when_current_model_faces_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "photo.jpg"
            source_path.write_bytes(b"stub")
            asset = self._asset(deleted=True)
            service = TrashService(session=None)
            service.asset_repository = _FakeAssetRepository(asset)
            service.people_maintenance = _FakePeopleMaintenance()
            service.face_repository = _FakeFaceRepository(has_current_faces=False)
            service.embedding_repository = _FakeEmbeddingRepository(
                has_current_embedding=True
            )
            service.ai_model_repository = _FakeAIModelRepository()

            with (
                patch(
                    "app.services.trash.service.master_path_to_source_path",
                    return_value=source_path,
                ),
                patch(
                    "app.services.trash.service.TrashService._asset_needs_metadata_refresh",
                    return_value=False,
                ),
                patch(
                    "app.services.trash.service.enqueue_asset_faces_job",
                    new=AsyncMock(return_value=True),
                ) as face_job_mock,
            ):
                result = asyncio.run(service.restore_asset(asset.id))

        face_job_mock.assert_awaited_once_with(asset.id, force=False, auto_match=True)
        self.assertFalse(result.jobs.ran_face_matching)
        self.assertTrue(result.jobs.queued_face_job)
        self.assertFalse(result.jobs.queued_embedding_job)

    def test_restore_asset_rejects_missing_source_file(self) -> None:
        asset = self._asset(deleted=True)
        service = TrashService(session=None)
        service.asset_repository = _FakeAssetRepository(asset)

        with patch(
            "app.services.trash.service.master_path_to_source_path",
            return_value=Path("/tmp/does-not-exist.jpg"),
        ):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(service.restore_asset(asset.id))

        self.assertEqual(exc.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
