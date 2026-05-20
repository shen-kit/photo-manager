from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from starlette.requests import Request

from app.api.v1.features.trash import (
    get_deleted_asset,
    list_deleted_assets,
    restore_deleted_asset,
    restore_deleted_assets,
)
from app.models import Asset, User
from app.services.trash.schemas import TrashBulkRestoreRequest
from app.services.trash.service import TrashRestoreJobResult, TrashRestoreResult


class _FakeTrashService:
    def __init__(self) -> None:
        self.list_calls: list[tuple[int, int, str]] = []
        self.detail_calls: list[str] = []
        self.restore_calls: list[str] = []
        self.bulk_calls: list[list[str]] = []
        self.deleted_rows = []
        self.detail_row = None
        self.restore_result = None
        self.bulk_result = ([], [])

    def list_deleted_assets(self, *, page, page_size, sort):
        self.list_calls.append((page, page_size, sort))
        return len(self.deleted_rows), list(self.deleted_rows)

    def get_deleted_asset_detail(self, asset_id):
        self.detail_calls.append(str(asset_id))
        return self.detail_row

    async def restore_asset(self, asset_id):
        self.restore_calls.append(str(asset_id))
        return self.restore_result

    async def restore_assets(self, asset_ids):
        self.bulk_calls.append([str(asset_id) for asset_id in asset_ids])
        return self.bulk_result


class TrashApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user = User(
            id=uuid4(),
            username="tester",
            password_hash="x",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("testserver", 80),
                "headers": [],
            }
        )

    def _asset(self, *, deleted: bool = True) -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2024/test.jpg",
            mime_type="image/jpeg",
            has_large_preview=True,
            created_at=datetime.now(timezone.utc),
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )

    def _restore_result(self, asset: Asset) -> TrashRestoreResult:
        return TrashRestoreResult(
            asset=asset,
            tags=[],
            faces=[],
            jobs=TrashRestoreJobResult(
                queued_metadata_job=False,
                queued_embedding_job=True,
                queued_face_job=False,
                ran_face_matching=True,
                matched_faces=1,
            ),
        )

    def test_list_deleted_assets_passes_sort_and_returns_deleted_only_payload(
        self,
    ) -> None:
        asset = self._asset(deleted=True)
        service = _FakeTrashService()
        service.deleted_rows = [(asset, [], [])]

        response = list_deleted_assets(
            request=self.request,
            page=2,
            page_size=25,
            sort="taken_at_desc",
            trash_service=service,
            current_user=self.user,
        )

        self.assertEqual(service.list_calls, [(2, 25, "taken_at_desc")])
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].id, asset.id)
        self.assertEqual(response.items[0].deleted_at, asset.deleted_at)

    def test_get_deleted_asset_returns_deleted_detail(self) -> None:
        asset = self._asset(deleted=True)
        service = _FakeTrashService()
        service.detail_row = (asset, [], [])

        response = get_deleted_asset(
            asset_id=asset.id,
            request=self.request,
            trash_service=service,
            current_user=self.user,
        )

        self.assertEqual(service.detail_calls, [str(asset.id)])
        self.assertEqual(response.id, asset.id)
        self.assertEqual(response.deleted_at, asset.deleted_at)

    def test_single_restore_returns_job_summary(self) -> None:
        deleted_asset = self._asset(deleted=False)
        service = _FakeTrashService()
        service.restore_result = self._restore_result(deleted_asset)

        response = asyncio.run(
            restore_deleted_asset(
                asset_id=deleted_asset.id,
                request=self.request,
                trash_service=service,
                current_user=self.user,
            )
        )

        self.assertEqual(service.restore_calls, [str(deleted_asset.id)])
        self.assertEqual(response.asset.id, deleted_asset.id)
        self.assertTrue(response.jobs.ran_face_matching)
        self.assertTrue(response.jobs.queued_embedding_job)

    def test_bulk_restore_returns_partial_failures(self) -> None:
        restored_asset = self._asset(deleted=False)
        missing_id = uuid4()
        service = _FakeTrashService()
        service.bulk_result = (
            [self._restore_result(restored_asset)],
            [(missing_id, "Asset not found in trash")],
        )

        response = asyncio.run(
            restore_deleted_assets(
                payload=TrashBulkRestoreRequest(
                    asset_ids=[restored_asset.id, missing_id]
                ),
                request=self.request,
                trash_service=service,
                current_user=self.user,
            )
        )

        self.assertEqual(
            service.bulk_calls,
            [[str(restored_asset.id), str(missing_id)]],
        )
        self.assertEqual(response.restored, 1)
        self.assertEqual(response.failed, 1)
        self.assertEqual(response.failures[0].asset_id, missing_id)


if __name__ == "__main__":
    unittest.main()
