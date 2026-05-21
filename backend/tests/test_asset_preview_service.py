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

        self.assertTrue(
            response.preview_url.endswith(f"/api/v1/assets/{asset.id}/preview")
        )

    def test_small_image_preview_uses_original_file(self) -> None:
        asset = self._asset(has_large_preview=False)
        session = _FakeSession(asset)
        service = AssetPreviewService(session)

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            with patch(
                "app.services.assets.preview.master_path_to_source_path",
                return_value=image_path,
            ):
                resolution = self._run_async(service.resolve_preview(asset.id))

        self.assertFalse(resolution.queued)
        self.assertEqual(resolution.file_path, image_path)

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
                resolution = self._run_async(service.resolve_preview(asset.id))

        self.assertFalse(resolution.queued)
        self.assertEqual(resolution.file_path, preview_path)
        self.assertEqual(asset.preview_status, "ready")

    @staticmethod
    def _run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
