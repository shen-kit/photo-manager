from __future__ import annotations

import asyncio
import os
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
from app.services.processing_dag import ProcessingFollowUpResult
from app.services.trash.service import TrashService


class _FakeAssetRepository:
    def __init__(self, assets: list[Asset] | None = None) -> None:
        self.assets = {asset.id: asset for asset in (assets or [])}
        self.restored_ids: list[str] = []
        self.deleted_ids: list[str] = []

    def get_deleted_asset(self, asset_id):
        asset = self.assets.get(asset_id)
        if asset is not None and asset.deleted_at is not None:
            return asset
        return None

    def restore_deleted_asset(self, asset):
        asset.deleted_at = None
        self.restored_ids.append(str(asset.id))
        self.assets[asset.id] = asset
        return asset

    def get_active_asset_detail(self, asset_id):
        asset = self.assets.get(asset_id)
        if asset is None or asset.deleted_at is not None:
            return None
        return (asset, [], [])

    def list_all_deleted_assets(self):
        return [asset for asset in self.assets.values() if asset.deleted_at is not None]

    def delete_asset_record(self, asset):
        self.deleted_ids.append(str(asset.id))
        self.assets.pop(asset.id, None)


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
            service.asset_repository = _FakeAssetRepository([asset])
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
                    "app.services.trash.service.AssetProcessingDagService.schedule_restore_follow_up",
                    new=AsyncMock(
                        return_value=ProcessingFollowUpResult(
                            queued_metadata_job=False,
                            queued_embedding_job=True,
                            queued_face_job=False,
                            ran_face_matching=True,
                            matched_faces=1,
                        )
                    ),
                ) as follow_up_mock,
            ):
                result = asyncio.run(service.restore_asset(asset.id))

        self.assertIsNone(result.asset.deleted_at)
        self.assertEqual(service.asset_repository.restored_ids, [str(asset.id)])
        self.assertEqual(
            service.people_maintenance.restore_calls,
            [str(asset.id)],
        )
        follow_up_mock.assert_awaited_once_with(asset.id)
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
            service.asset_repository = _FakeAssetRepository([asset])
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
                    "app.services.trash.service.AssetProcessingDagService.schedule_restore_follow_up",
                    new=AsyncMock(
                        return_value=ProcessingFollowUpResult(
                            queued_metadata_job=False,
                            queued_embedding_job=False,
                            queued_face_job=True,
                            ran_face_matching=False,
                            matched_faces=0,
                        )
                    ),
                ) as follow_up_mock,
            ):
                result = asyncio.run(service.restore_asset(asset.id))

        follow_up_mock.assert_awaited_once_with(asset.id)
        self.assertFalse(result.jobs.ran_face_matching)
        self.assertTrue(result.jobs.queued_face_job)
        self.assertFalse(result.jobs.queued_embedding_job)

    def test_restore_asset_rejects_missing_source_file(self) -> None:
        asset = self._asset(deleted=True)
        service = TrashService(session=None)
        service.asset_repository = _FakeAssetRepository([asset])

        with patch(
            "app.services.trash.service.master_path_to_source_path",
            return_value=Path("/tmp/does-not-exist.jpg"),
        ):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(service.restore_asset(asset.id))

        self.assertEqual(exc.exception.status_code, 409)

    def test_permanently_delete_asset_removes_files_and_deletes_record(self) -> None:
        with tempfile.TemporaryDirectory() as originals_dir, tempfile.TemporaryDirectory() as processed_dir:
            asset = self._asset(deleted=True)
            source_path = Path(originals_dir) / asset.master_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"original")
            generated_dir = Path(processed_dir) / "assets" / str(asset.id)
            generated_dir.mkdir(parents=True, exist_ok=True)
            (generated_dir / "small.webp").write_bytes(b"small")

            service = TrashService(session=MagicMock())
            service.asset_repository = _FakeAssetRepository([asset])

            with patch.dict(
                os.environ,
                {
                    "MEDIA_ORIGINALS_DIR": originals_dir,
                    "MEDIA_PROCESSED_DIR": processed_dir,
                },
                clear=False,
            ):
                with (
                    patch(
                        "app.services.trash.service.master_path_to_source_path",
                        return_value=source_path,
                    ),
                    patch(
                        "app.services.trash.service.processed_asset_dir",
                        return_value=generated_dir,
                    ),
                    patch(
                        "app.services.trash.service.MEDIA_PROCESSED_DIR",
                        new=Path(processed_dir).resolve(),
                    ),
                ):
                    result = service.permanently_delete_asset(asset.id)

        self.assertEqual(result.asset_id, asset.id)
        self.assertFalse(source_path.exists())
        self.assertFalse(generated_dir.exists())
        self.assertEqual(service.asset_repository.deleted_ids, [str(asset.id)])

    def test_permanently_delete_asset_rejects_active_asset(self) -> None:
        asset = self._asset(deleted=False)
        service = TrashService(session=MagicMock())
        service.asset_repository = _FakeAssetRepository([asset])

        with self.assertRaises(HTTPException) as exc:
            service.permanently_delete_asset(asset.id)

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(service.asset_repository.deleted_ids, [])

    def test_bulk_permanent_delete_deduplicates_and_reports_failures(self) -> None:
        deleted_asset = self._asset(deleted=True)
        active_asset = self._asset(deleted=False)
        service = TrashService(session=MagicMock())
        service.asset_repository = _FakeAssetRepository([deleted_asset, active_asset])

        with (
            patch.object(service, "_delete_asset_files") as delete_files_mock,
        ):
            summary = service.permanently_delete_assets(
                [deleted_asset.id, deleted_asset.id, active_asset.id]
            )

        self.assertEqual([item.asset_id for item in summary.deleted], [deleted_asset.id])
        self.assertEqual(summary.failures, [(active_asset.id, "Asset not found in trash")])
        delete_files_mock.assert_called_once_with(deleted_asset)
        self.assertEqual(service.asset_repository.deleted_ids, [str(deleted_asset.id)])

    def test_empty_trash_deletes_only_trashed_assets(self) -> None:
        deleted_asset = self._asset(deleted=True)
        active_asset = self._asset(deleted=False)
        service = TrashService(session=MagicMock())
        service.asset_repository = _FakeAssetRepository([deleted_asset, active_asset])

        with patch.object(service, "_delete_asset_files") as delete_files_mock:
            summary = service.empty_trash()

        self.assertEqual([item.asset_id for item in summary.deleted], [deleted_asset.id])
        self.assertEqual(summary.failures, [])
        delete_files_mock.assert_called_once_with(deleted_asset)
        self.assertEqual(service.asset_repository.deleted_ids, [str(deleted_asset.id)])

    def test_permanently_delete_asset_allows_missing_files(self) -> None:
        asset = self._asset(deleted=True)
        service = TrashService(session=MagicMock())
        service.asset_repository = _FakeAssetRepository([asset])

        with (
            patch(
                "app.services.trash.service.master_path_to_source_path",
                return_value=Path("/tmp/missing-original.jpg"),
            ),
            patch(
                "app.services.trash.service.processed_asset_dir",
                return_value=Path("/tmp/missing-processed"),
            ),
            patch(
                "app.services.trash.service.MEDIA_PROCESSED_DIR",
                new=Path("/tmp").resolve(),
            ),
        ):
            service.permanently_delete_asset(asset.id)

        self.assertEqual(service.asset_repository.deleted_ids, [str(asset.id)])

    def test_permanently_delete_asset_rejects_invalid_processed_dir(self) -> None:
        asset = self._asset(deleted=True)
        service = TrashService(session=MagicMock())
        service.asset_repository = _FakeAssetRepository([asset])

        with (
            patch(
                "app.services.trash.service.master_path_to_source_path",
                return_value=Path("/tmp/original.jpg"),
            ),
            patch(
                "app.services.trash.service.processed_asset_dir",
                return_value=Path("/var/outside"),
            ),
            patch(
                "app.services.trash.service.MEDIA_PROCESSED_DIR",
                new=Path("/tmp").resolve(),
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                service.permanently_delete_asset(asset.id)

        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(service.asset_repository.deleted_ids, [])


if __name__ == "__main__":
    unittest.main()
