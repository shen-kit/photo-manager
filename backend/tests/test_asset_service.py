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

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1


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
            patch("app.services.assets.service.PeopleMaintenanceService") as maintenance_cls,
        ):
            repo = repo_cls.return_value
            impacted_person_ids = [uuid4(), uuid4()]
            repo.list_person_ids_for_asset.return_value = impacted_person_ids
            maintenance = maintenance_cls.return_value

            service.delete_asset(asset.id)

        self.assertIsNotNone(asset.deleted_at)
        self.assertEqual(session.commit_count, 1)
        repo.list_person_ids_for_asset.assert_called_once_with(asset_id=asset.id)
        maintenance.reconcile_people.assert_called_once_with(person_ids=impacted_person_ids)


if __name__ == "__main__":
    unittest.main()
