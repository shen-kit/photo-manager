from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.models import AIModel, Asset
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
)
from app.services.processing_dag import (
    AssetProcessingDagService,
    AssetProcessingDagStateService,
    NODE_CLIP_EMBEDDING,
    NODE_FACE_PROCESSING,
    NODE_METADATA_REFRESH,
    NODE_SMALL_THUMBNAIL,
)


class _FakeSession:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = {asset.id: asset for asset in assets}

    def get(self, model, asset_id):
        del model
        return self.assets.get(asset_id)


class _FakeAssetProcessingRepository:
    def __init__(self, states: dict[tuple[str, int | None], object] | None = None) -> None:
        self.states = states or {}

    def get_state(self, *, asset_id, ai_model_id, task):
        del asset_id
        return self.states.get(
            (task, ai_model_id),
            SimpleNamespace(row=None, last_job=None),
        )


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
            model_name="face",
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


class _FakeEmbeddingRepository:
    def __init__(self, *, has_embedding: bool = False) -> None:
        self.has_embedding = has_embedding

    def asset_has_embedding(self, asset, model_id: int) -> bool:
        del asset, model_id
        return self.has_embedding


class _FakeFaceRepository:
    def __init__(self, *, has_faces: bool = False) -> None:
        self.has_faces = has_faces

    def asset_has_faces(self, *, asset_id, model_id: int) -> bool:
        del asset_id, model_id
        return self.has_faces


class ProcessingDagStateTest(unittest.TestCase):
    def _asset(self, *, mime_type: str = "image/jpeg") -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2026/05/photo.jpg",
            mime_type=mime_type,
            has_large_preview=True,
            file_size_bytes=1024,
            created_at=datetime.now(timezone.utc),
        )

    def test_video_clip_is_blocked_by_missing_small_thumbnail(self) -> None:
        asset = self._asset(mime_type="video/mp4")
        state_service = AssetProcessingDagStateService(
            _FakeSession([asset]),
            asset_processing_repository=_FakeAssetProcessingRepository(
                {
                    (NODE_METADATA_REFRESH, None): SimpleNamespace(
                        row=SimpleNamespace(status="completed"),
                        last_job=SimpleNamespace(status="completed"),
                    )
                }
            ),
            ai_model_repository=_FakeAIModelRepository(),
            embedding_repository=_FakeEmbeddingRepository(has_embedding=False),
            face_repository=_FakeFaceRepository(),
        )

        with patch(
            "app.services.processing_dag.state.processed_asset_dir",
            return_value=Path("/tmp/nonexistent"),
        ):
            node = state_service.evaluate(asset=asset, task=NODE_CLIP_EMBEDDING)

        self.assertTrue(node.blocked_by_dependencies)
        self.assertIn(NODE_SMALL_THUMBNAIL, node.dependencies)
        self.assertFalse(node.needs_processing)

    def test_clip_node_is_stale_when_model_id_mismatches(self) -> None:
        asset = self._asset()
        asset.search_vector = [0.1, 0.2]
        asset.search_model_id = 3
        state_service = AssetProcessingDagStateService(
            _FakeSession([asset]),
            asset_processing_repository=_FakeAssetProcessingRepository(
                {
                    (NODE_METADATA_REFRESH, None): SimpleNamespace(
                        row=SimpleNamespace(status="completed"),
                        last_job=SimpleNamespace(status="completed"),
                    )
                }
            ),
            ai_model_repository=_FakeAIModelRepository(clip_model_id=11),
            embedding_repository=_FakeEmbeddingRepository(has_embedding=False),
            face_repository=_FakeFaceRepository(),
        )

        node = state_service.evaluate(asset=asset, task=NODE_CLIP_EMBEDDING)

        self.assertTrue(node.stale)
        self.assertTrue(node.needs_processing)

    def test_running_node_with_inactive_job_is_retryable(self) -> None:
        asset = self._asset()
        state_service = AssetProcessingDagStateService(
            _FakeSession([asset]),
            asset_processing_repository=_FakeAssetProcessingRepository(
                {
                    (NODE_METADATA_REFRESH, None): SimpleNamespace(
                        row=SimpleNamespace(status="running"),
                        last_job=SimpleNamespace(status="failed"),
                    )
                }
            ),
            ai_model_repository=_FakeAIModelRepository(),
            embedding_repository=_FakeEmbeddingRepository(),
            face_repository=_FakeFaceRepository(),
        )

        node = state_service.evaluate(asset=asset, task=NODE_METADATA_REFRESH)

        self.assertTrue(node.retryable)
        self.assertTrue(node.needs_processing)

    def test_force_face_processing_still_respects_applicability(self) -> None:
        asset = self._asset(mime_type="video/mp4")
        state_service = AssetProcessingDagStateService(
            _FakeSession([asset]),
            asset_processing_repository=_FakeAssetProcessingRepository(),
            ai_model_repository=_FakeAIModelRepository(),
            embedding_repository=_FakeEmbeddingRepository(),
            face_repository=_FakeFaceRepository(),
        )

        node = state_service.evaluate(
            asset=asset,
            task=NODE_FACE_PROCESSING,
            force=True,
        )

        self.assertFalse(node.applicable)
        self.assertFalse(node.needs_processing)


class ProcessingDagExecutorTest(unittest.TestCase):
    def _asset(self) -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2026/05/photo.jpg",
            mime_type="image/jpeg",
            has_large_preview=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_schedule_restore_runs_incremental_matching_when_faces_exist(self) -> None:
        asset = self._asset()
        session = _FakeSession([asset])

        with (
            patch(
                "app.services.processing_dag.executor.AssetProcessingDagStateService",
            ) as state_cls,
            patch(
                "app.services.processing_dag.executor.FaceAssignmentService.assign_faces_for_asset",
                return_value=SimpleNamespace(faces_matched=2),
            ) as match_mock,
            patch(
                "app.services.processing_dag.executor.AssetProcessingTrackerService.mark_completed"
            ) as tracker_complete,
        ):
            state = state_cls.return_value
            state.get_asset.return_value = asset

            def evaluate(*, asset, task, force=False, require_face_match=False):
                del asset, force, require_face_match
                if task == NODE_FACE_PROCESSING:
                    return SimpleNamespace(completed=True, needs_processing=False)
                return SimpleNamespace(completed=False, needs_processing=False)

            state.evaluate.side_effect = evaluate
            result = asyncio.run(
                AssetProcessingDagService(session).schedule_restore_follow_up(asset.id)
            )

        match_mock.assert_called_once_with(asset.id)
        tracker_complete.assert_called()
        self.assertTrue(result.ran_face_matching)
        self.assertEqual(result.matched_faces, 2)
        self.assertFalse(result.queued_face_job)

    def test_schedule_asset_created_queues_metadata_when_incomplete(self) -> None:
        asset = self._asset()
        session = _FakeSession([asset])

        with (
            patch(
                "app.services.processing_dag.executor.AssetProcessingDagStateService",
            ) as state_cls,
            patch(
                "app.services.processing_dag.executor.enqueue_asset_processing_job",
                new=AsyncMock(return_value=True),
            ) as enqueue_mock,
        ):
            state = state_cls.return_value
            state.get_asset.return_value = asset
            state.evaluate.return_value = SimpleNamespace(needs_processing=True)

            queued = asyncio.run(
                AssetProcessingDagService(session).schedule_asset_created(asset.id)
            )

        self.assertTrue(queued)
        enqueue_mock.assert_awaited_once_with(asset.id, parent_job_id=None)

    def test_plan_scan_asset_returns_shared_scan_policy_outcomes(self) -> None:
        asset = self._asset()
        session = _FakeSession([asset])

        with patch(
            "app.services.processing_dag.executor.AssetProcessingDagStateService",
        ) as state_cls:
            state = state_cls.return_value
            state.get_asset.return_value = asset
            state.evaluate.side_effect = [
                SimpleNamespace(needs_processing=True),
                SimpleNamespace(needs_processing=False),
                SimpleNamespace(needs_processing=True),
                SimpleNamespace(needs_processing=True),
            ]

            plan = AssetProcessingDagService(session).plan_scan_asset(asset.id)

        self.assertTrue(plan.require_tiny_thumbnail)
        self.assertFalse(plan.require_small_thumbnail)
        self.assertTrue(plan.queue_clip)
        self.assertTrue(plan.queue_faces)


if __name__ == "__main__":
    unittest.main()
