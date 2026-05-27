from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.models import Asset
from app.services.assets.service import AssetService


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.refreshed: list[object] = []

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, value) -> None:
        self.refreshed.append(value)

    def rollback(self) -> None:
        return None

    def exec(self, statement):
        del statement

        class _Result:
            @staticmethod
            def first():
                return None

        return _Result()


class AssetServiceTest(unittest.TestCase):
    def test_delete_asset_reconciles_impacted_people(self) -> None:
        asset = Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2024/test.jpg",
            mime_type="image/jpeg",
            created_at=datetime.now(timezone.utc),
        )
        session = _FakeSession()
        service = AssetService(session=session)
        service._get_active_asset_or_404 = Mock(return_value=asset)

        with (
            patch("app.services.assets.service.PeopleRepository") as repo_cls,
            patch(
                "app.services.assets.service.PeopleMaintenanceService"
            ) as maintenance_cls,
        ):
            repo = repo_cls.return_value
            impacted_person_ids = [uuid4(), uuid4()]
            repo.list_person_ids_for_asset.return_value = impacted_person_ids
            maintenance = maintenance_cls.return_value

            service.delete_asset(asset.id)

        self.assertIsNotNone(asset.deleted_at)
        self.assertEqual(session.commit_count, 1)
        repo.list_person_ids_for_asset.assert_called_once_with(asset_id=asset.id)
        maintenance.reconcile_people.assert_called_once_with(
            person_ids=impacted_person_ids
        )

    def test_process_new_asset_uses_dag_entrypoint_for_new_asset(self) -> None:
        session = _FakeSession()
        service = AssetService(session=session)
        source_path = Mock()
        source_path.stat.return_value.st_size = 1234

        with (
            patch.object(
                service,
                "resolve_original_path",
                return_value=("2026/05/photo.jpg", source_path),
            ),
            patch("app.services.assets.service.guess_mime_type", return_value="image/jpeg"),
            patch("app.services.assets.service.compute_sha256", return_value="hash"),
            patch.object(
                service,
                "_inspect_media_or_raise",
                return_value=(800, 600, None),
            ),
            patch.object(
                service,
                "_ensure_canonical_original_location",
                return_value=("2026/05/photo.jpg", source_path),
            ),
            patch("app.services.assets.service.AssetProcessingDagService") as dag_cls,
            patch("app.services.assets.service.should_generate_large_preview", return_value=False),
            patch("app.services.assets.service.is_supported_image_mime_type", return_value=False),
            patch("app.services.assets.service.is_supported_video_mime_type", return_value=False),
        ):
            dag_cls.return_value.schedule_asset_created = Mock()
            async def _scheduled(asset_id):
                del asset_id
                return True
            dag_cls.return_value.schedule_asset_created.side_effect = _scheduled
            result = self._run_async(service.process_new_asset("ignored", uuid4()))

        self.assertTrue(result.queued_job)

    @staticmethod
    def _run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
