from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import AIModel, Asset
from app.services.ai_models.repository import AI_MODEL_TASK_FACE_RECOGNITION
from app.services.face_detection.service import DetectedFace, FaceBoundingBox
from app.services.faces.service import FaceProcessingService


class _FakeAIModelRepository:
    def __init__(self, model: AIModel) -> None:
        self.model = model

    def get_default_model_for_task(self, task: str) -> AIModel:
        if task != AI_MODEL_TASK_FACE_RECOGNITION:
            raise AssertionError(task)
        return self.model


class _FakeFaceRepository:
    def __init__(
        self,
        *,
        asset: Asset,
        total_existing: int = 0,
        confirmed_existing: int = 0,
        confirmed_boxes: list[dict[str, int]] | None = None,
    ) -> None:
        self.asset = asset
        self.total_existing = total_existing
        self.confirmed_existing = confirmed_existing
        self.confirmed_boxes = confirmed_boxes or []
        self.deleted_unconfirmed_calls: list[tuple[str, int]] = []
        self.inserted_faces = []

    def get_asset(self, asset_id):
        return self.asset if asset_id == self.asset.id else None

    def count_faces(self, *, asset_id, model_id):
        return self.total_existing

    def count_confirmed_faces(self, *, asset_id, model_id):
        return self.confirmed_existing

    def list_confirmed_bounding_boxes(self, *, asset_id, model_id):
        return list(self.confirmed_boxes)

    def delete_unconfirmed_faces(self, *, asset_id, model_id):
        self.deleted_unconfirmed_calls.append((str(asset_id), model_id))
        return self.total_existing - self.confirmed_existing

    def insert_faces(self, *, faces):
        self.inserted_faces.extend(faces)

    def count_assets_pending_face_processing(self, *, model_id, force):
        return 0

    def list_asset_ids_pending_face_processing(
        self, *, model_id, force, limit=None, offset=0
    ):
        return []


class _FakeAIProcessingRepository:
    def __init__(self, *, completed: bool = False) -> None:
        self.completed = completed

    def asset_has_completed_processing(self, *, asset_id, ai_model_id, task):
        del asset_id, ai_model_id, task
        return self.completed

    def list_asset_ids_needing_face_processing(
        self, *, ai_model_id, limit=None, offset=0
    ):
        del ai_model_id, limit, offset
        return []


class FaceProcessingServiceTest(unittest.TestCase):
    def _asset(self, path: Path, *, mime_type: str = "image/jpeg") -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path=path.name,
            mime_type=mime_type,
            has_large_preview=False,
            created_at=datetime.now(timezone.utc),
        )

    def _model(self, model_id: int = 7) -> AIModel:
        return AIModel(
            id=model_id,
            task=AI_MODEL_TASK_FACE_RECOGNITION,
            model_name="insightface-buffalo_l",
            version_tag="buffalo_l",
            vector_dimensions=512,
            is_deprecated=False,
        )

    def _face(self, x: int, y: int) -> DetectedFace:
        return DetectedFace(
            bounding_box=FaceBoundingBox(
                x=x,
                y=y,
                width=10,
                height=12,
                image_width=100,
                image_height=80,
            ),
            confidence=0.99,
            embedding=[0.1] * 512,
            landmarks=None,
        )

    def test_force_false_skips_when_faces_already_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            repo = _FakeFaceRepository(
                asset=asset, total_existing=2, confirmed_existing=1
            )
            detector_calls = []
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                detector=lambda path: detector_calls.append(path) or [],
            )

            from unittest.mock import patch

            with patch(
                "app.services.faces.service.master_path_to_source_path",
                return_value=image_path,
            ):
                result = service.process_asset_faces(asset.id, force=False)

        self.assertTrue(result.skipped)
        self.assertFalse(result.processed)
        self.assertEqual(detector_calls, [])
        self.assertEqual(repo.inserted_faces, [])

    def test_force_true_preserves_confirmed_faces_and_recreates_unconfirmed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            confirmed_box = {
                "x": 1,
                "y": 2,
                "width": 10,
                "height": 12,
                "image_width": 100,
                "image_height": 80,
            }
            repo = _FakeFaceRepository(
                asset=asset,
                total_existing=2,
                confirmed_existing=1,
                confirmed_boxes=[confirmed_box],
            )
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                detector=lambda path: [self._face(1, 2), self._face(30, 20)],
            )

            from unittest.mock import patch

            with patch(
                "app.services.faces.service.master_path_to_source_path",
                return_value=image_path,
            ):
                result = service.process_asset_faces(asset.id, force=True)

        self.assertTrue(result.processed)
        self.assertFalse(result.skipped)
        self.assertEqual(result.deleted_unconfirmed_faces, 1)
        self.assertEqual(result.detected_faces, 2)
        self.assertEqual(result.faces_created, 1)
        self.assertEqual(len(repo.inserted_faces), 1)
        self.assertEqual(repo.inserted_faces[0].bounding_box["x"], 30)

    def test_force_true_skips_when_only_confirmed_faces_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            repo = _FakeFaceRepository(
                asset=asset, total_existing=2, confirmed_existing=2
            )
            detector_calls = []
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                detector=lambda path: detector_calls.append(path) or [],
            )

            from unittest.mock import patch

            with patch(
                "app.services.faces.service.master_path_to_source_path",
                return_value=image_path,
            ):
                result = service.process_asset_faces(asset.id, force=True)

        self.assertTrue(result.skipped)
        self.assertEqual(detector_calls, [])
        self.assertEqual(repo.inserted_faces, [])

    def test_process_uses_default_model_id_for_inserted_faces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            repo = _FakeFaceRepository(asset=asset)
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model(model_id=42)),
                detector=lambda path: [self._face(5, 6)],
            )

            from unittest.mock import patch

            with patch(
                "app.services.faces.service.master_path_to_source_path",
                return_value=image_path,
            ):
                result = service.process_asset_faces(asset.id, force=False)

        self.assertEqual(result.model_id, 42)
        self.assertEqual(repo.inserted_faces[0].face_model_id, 42)

    def test_non_image_assets_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "clip.mp4"
            path.write_bytes(b"stub")
            asset = self._asset(path, mime_type="video/mp4")
            repo = _FakeFaceRepository(asset=asset)
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                detector=lambda path: [self._face(5, 6)],
            )

            result = service.process_asset_faces(asset.id, force=False)

        self.assertTrue(result.skipped)
        self.assertEqual(repo.inserted_faces, [])

    def test_completed_zero_face_processing_row_skips_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            repo = _FakeFaceRepository(
                asset=asset, total_existing=0, confirmed_existing=0
            )
            detector_calls = []
            service = FaceProcessingService(
                session=None,
                repository=repo,
                ai_processing_repository=_FakeAIProcessingRepository(completed=True),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                detector=lambda path: detector_calls.append(path) or [self._face(5, 6)],
            )

            result = service.process_asset_faces(asset.id, force=False)

        self.assertTrue(result.skipped)
        self.assertFalse(result.processed)
        self.assertEqual(result.detected_faces, 0)
        self.assertEqual(detector_calls, [])


if __name__ == "__main__":
    unittest.main()
