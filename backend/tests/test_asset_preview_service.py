from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from starlette.requests import Request

from app.api.v1.features.assets.router import _build_detail_response
from app.models import Asset
from app.services.assets.preview import AssetPreviewService


class _FakeSession:
    def __init__(self, asset: Asset) -> None:
        self.asset = asset
        self.added: list[object] = []
        self.commit_count = 0

    def get(self, model, asset_id):
        del model
        return self.asset if self.asset.id == asset_id else None

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1

    def exec(self, statement):
        del statement

        class _Result:
            def __init__(self, asset: Asset) -> None:
                self._asset = asset

            def all(self):
                return [self._asset]

        return _Result(self.asset)


class AssetPreviewServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("testserver", 80),
                "headers": [],
            }
        )

    def _asset(
        self,
        *,
        mime_type: str = "image/jpeg",
        has_large_preview: bool = False,
    ) -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path="2024/test.jpg",
            mime_type=mime_type,
            has_large_preview=has_large_preview,
            created_at=datetime.now(timezone.utc),
        )

    def test_detail_response_uses_preview_url_field(self) -> None:
        asset = self._asset()

        response = _build_detail_response(self.request, asset, [], [])

        self.assertTrue(response.preview_url.endswith("/media/originals/2024/test.jpg"))

    def test_small_image_preview_is_ready_with_original_url(self) -> None:
        asset = self._asset(has_large_preview=False)
        session = _FakeSession(asset)
        service = AssetPreviewService(session)

        items = self._run_async(
            service.ensure_previews(
                asset_ids=[asset.id],
                base_url="http://testserver/",
                priority="low",
            )
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "ready")
        self.assertTrue(items[0].preview_url.endswith("/media/originals/2024/test.jpg"))
        self.assertIsNone(items[0].job_id)

    def test_video_preview_uses_existing_transcoded_file(self) -> None:
        asset = self._asset(mime_type="video/mp4")
        session = _FakeSession(asset)
        service = AssetPreviewService(session)

        with tempfile.TemporaryDirectory() as tmp_dir:
            preview_path = Path(tmp_dir) / "preview.mp4"
            preview_path.write_bytes(b"stub")
            with patch(
                "app.services.assets.preview.processed_video_preview_path",
                return_value=preview_path,
            ):
                items = self._run_async(
                    service.ensure_previews(
                        asset_ids=[asset.id],
                        base_url="http://testserver/",
                        priority="low",
                    )
                )

        self.assertEqual(items[0].status, "ready")
        self.assertTrue(
            items[0].preview_url.endswith(
                f"/media/processed/assets/{asset.id}/preview.mp4"
            )
        )
        self.assertEqual(asset.preview_status, "ready")

    def test_missing_asset_returns_not_found_status(self) -> None:
        asset = self._asset()
        session = _FakeSession(asset)
        service = AssetPreviewService(session)

        with patch.object(service, "_list_assets_by_ids", return_value={}):
            items = self._run_async(
                service.ensure_previews(
                    asset_ids=[uuid4()],
                    base_url="http://testserver/",
                    priority="low",
                )
            )

        self.assertEqual(items[0].status, "not_found")
        self.assertIsNone(items[0].preview_url)

    def test_preview_job_is_skipped_when_dag_state_is_already_satisfied(self) -> None:
        asset = self._asset(has_large_preview=True)
        session = _FakeSession(asset)
        service = AssetPreviewService(session)

        with patch(
            "app.services.assets.preview.AssetProcessingDagService"
        ) as dag_cls:
            dag_cls.return_value.evaluate.return_value = type(
                "State",
                (),
                {"needs_processing": False},
            )()
            job = self._run_async(
                service._ensure_preview_job(asset=asset, priority="low")
            )

        self.assertIsNone(job)

    @staticmethod
    def _run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
