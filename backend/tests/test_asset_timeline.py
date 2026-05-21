from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.services.assets.browse import (
    AssetGridFilters,
    AssetGridRow,
    decode_browse_cursor,
    encode_browse_cursor,
)
from app.services.assets.timeline import derive_asset_timeline_fields


class AssetTimelineTest(unittest.TestCase):
    def test_derive_uses_local_day_when_available(self) -> None:
        fields = derive_asset_timeline_fields(
            mime_type="image/jpeg",
            captured_at=datetime(2024, 5, 2, 1, 0, tzinfo=UTC),
            captured_at_local="2024-05-01T23:00:00-02:00",
            created_at=datetime(2024, 5, 3, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(fields.media_kind, "image")
        self.assertEqual(fields.timeline_day.isoformat(), "2024-05-01")
        self.assertEqual(fields.timeline_month.isoformat(), "2024-05-01")

    def test_derive_falls_back_to_created_at_when_captured_at_missing(self) -> None:
        fields = derive_asset_timeline_fields(
            mime_type="video/mp4",
            captured_at=None,
            captured_at_local=None,
            created_at=datetime(2024, 6, 15, 10, 30, tzinfo=UTC),
        )

        self.assertEqual(fields.media_kind, "video")
        self.assertEqual(fields.timeline_at, datetime(2024, 6, 15, 10, 30, tzinfo=UTC))
        self.assertEqual(fields.timeline_day.isoformat(), "2024-06-15")
        self.assertEqual(fields.timeline_month.isoformat(), "2024-06-01")

    def test_browse_cursor_rejects_scope_mismatch(self) -> None:
        row = AssetGridRow(
            id=uuid4(),
            mime_type="image/jpeg",
            media_kind="image",
            width=100,
            height=100,
            duration_seconds=None,
            is_favorite=False,
            captured_at=datetime(2024, 1, 2, 3, 4, tzinfo=UTC),
            timeline_at=datetime(2024, 1, 2, 3, 4, tzinfo=UTC),
            timeline_day=datetime(2024, 1, 2, 3, 4, tzinfo=UTC).date(),
            blurhash=None,
            has_large_preview=False,
        )
        cursor = encode_browse_cursor(filters=AssetGridFilters(), row=row)

        with self.assertRaises(HTTPException):
            decode_browse_cursor(
                cursor,
                filters=AssetGridFilters(media_kind="video"),
            )


if __name__ == "__main__":
    unittest.main()
