from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import Asset
from app.services.assets.hashing import compute_sha256
from app.services.assets.storage_rules import StorageRulesService


class StorageRulesServiceTest(unittest.TestCase):
    def _asset(self, *, master_path: str, file_hash: str) -> Asset:
        return Asset(
            id=uuid4(),
            file_hash=file_hash,
            master_path=master_path,
            mime_type="image/jpeg",
            created_at=datetime.now(timezone.utc),
        )

    def test_reconcile_duplicate_source_deletes_old_path(self) -> None:
        service = StorageRulesService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_path = root / "legacy" / "photo.jpg"
            target_path = root / "2026" / "05" / "hash.jpg"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"same-bytes")
            target_path.write_bytes(b"same-bytes")
            file_hash = compute_sha256(source_path)
            canonical_target = target_path.with_name(f"{file_hash}.jpg")
            target_path.rename(canonical_target)
            asset = self._asset(master_path="legacy/photo.jpg", file_hash=file_hash)

            action = service._reconcile_asset(
                asset=asset,
                source_path=source_path,
                target_path=canonical_target,
                target_master_path=f"2026/05/{file_hash}.jpg",
                dry_run=False,
            )

            self.assertEqual(action.kind, "reconciled_db_stale")
            self.assertEqual(asset.master_path, f"2026/05/{file_hash}.jpg")
            self.assertFalse(source_path.exists())
            self.assertTrue(canonical_target.exists())

    def test_conflicting_target_keeps_old_path(self) -> None:
        service = StorageRulesService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_path = root / "legacy" / "photo.jpg"
            target_path = root / "2026" / "05" / "hash.jpg"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"source-bytes")
            target_path.write_bytes(b"different-bytes")
            file_hash = compute_sha256(source_path)
            canonical_target = target_path.with_name(f"{file_hash}.jpg")
            target_path.rename(canonical_target)
            asset = self._asset(master_path="legacy/photo.jpg", file_hash=file_hash)

            action = service._reconcile_asset(
                asset=asset,
                source_path=source_path,
                target_path=canonical_target,
                target_master_path=f"2026/05/{file_hash}.jpg",
                dry_run=False,
            )

            self.assertEqual(action.kind, "target_conflict")
            self.assertEqual(asset.master_path, "legacy/photo.jpg")
            self.assertTrue(source_path.exists())
            self.assertTrue(canonical_target.exists())


if __name__ == "__main__":
    unittest.main()
