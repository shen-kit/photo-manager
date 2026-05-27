from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from app.models import Asset
from app.services.manual_jobs.handlers import (
    ApplyStorageRulesManualJobHandler,
    ClusterFacesManualJobHandler,
    RegenerateMissingAssetThumbnailsManualJobHandler,
    RunMissingOrOutdatedClipEmbeddingsManualJobHandler,
    RunMissingOrOutdatedFaceRecognitionManualJobHandler,
)


class _FakeSession:
    def __init__(self, assets: list[Asset] | None = None) -> None:
        self.assets = assets or []

    def exec(self, statement):
        del statement

        class _Result:
            def __init__(self, assets: list[Asset]) -> None:
                self._assets = assets

            def all(self):
                return list(self._assets)

        return _Result(self.assets)


class _FakeEmbeddingService:
    def __init__(self, asset_ids):
        self.asset_ids = asset_ids

    def list_missing_asset_ids(self, *, force: bool):
        del force
        return 11, list(self.asset_ids)


class _FakeFaceService:
    def __init__(self, asset_ids):
        self.asset_ids = asset_ids

    def list_asset_ids_pending_face_processing(self, *, force: bool):
        del force
        return 17, list(self.asset_ids)


class ManualJobHandlersTest(unittest.TestCase):
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

    def test_thumbnail_handler_filters_candidates_through_dag(self) -> None:
        asset_a = self._asset()
        asset_b = self._asset()
        handler = RegenerateMissingAssetThumbnailsManualJobHandler(
            _FakeSession([asset_a, asset_b])
        )

        with patch(
            "app.services.manual_jobs.handlers.AssetProcessingDagService"
        ) as dag_cls:
            dag = dag_cls.return_value
            dag.plan_scan_asset.side_effect = [
                SimpleNamespace(
                    require_tiny_thumbnail=True,
                    require_small_thumbnail=False,
                ),
                SimpleNamespace(
                    require_tiny_thumbnail=False,
                    require_small_thumbnail=False,
                ),
            ]
            prepared = handler.prepare_run({})

        self.assertEqual(prepared.progress_total, 1)
        self.assertEqual(prepared.candidate_ids, [asset_a.id])

    def test_clip_prepare_run_filters_blocked_assets_with_dag(self) -> None:
        asset_a = self._asset()
        asset_b = self._asset(mime_type="video/mp4")
        handler = RunMissingOrOutdatedClipEmbeddingsManualJobHandler(_FakeSession())
        handler.embedding_service = _FakeEmbeddingService([asset_a.id, asset_b.id])

        with patch(
            "app.services.manual_jobs.handlers.AssetProcessingDagService"
        ) as dag_cls:
            dag = dag_cls.return_value
            dag.state.get_asset.side_effect = [asset_a, asset_b]
            dag.evaluate.side_effect = [
                SimpleNamespace(needs_processing=True),
                SimpleNamespace(needs_processing=False),
            ]
            prepared = handler.prepare_run({"force": False})

        self.assertEqual(prepared.progress_total, 1)
        self.assertEqual(prepared.candidate_ids, [asset_a.id])

    def test_face_prepare_run_filters_assets_with_dag(self) -> None:
        asset_a = self._asset()
        asset_b = self._asset()
        handler = RunMissingOrOutdatedFaceRecognitionManualJobHandler(_FakeSession())
        handler.face_service = _FakeFaceService([asset_a.id, asset_b.id])

        with patch(
            "app.services.manual_jobs.handlers.AssetProcessingDagService"
        ) as dag_cls:
            dag = dag_cls.return_value
            dag.state.get_asset.side_effect = [asset_a, asset_b]
            dag.evaluate.side_effect = [
                SimpleNamespace(needs_processing=False),
                SimpleNamespace(needs_processing=True),
            ]
            prepared = handler.prepare_run({"force": False, "auto_match": True})

        self.assertEqual(prepared.progress_total, 1)
        self.assertEqual(prepared.candidate_ids, [asset_b.id])

    def test_global_and_api_manual_jobs_remain_outside_asset_dag(self) -> None:
        cluster = ClusterFacesManualJobHandler(_FakeSession())
        storage = ApplyStorageRulesManualJobHandler(_FakeSession())

        self.assertEqual(cluster.definition.mode, "global")
        self.assertEqual(storage.definition.execution_backend, "api")
        self.assertEqual(storage.definition.mode, "global")


if __name__ == "__main__":
    unittest.main()
