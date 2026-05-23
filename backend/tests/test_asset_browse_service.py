from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.services.assets.browse import (
    AssetGridFilters,
    AssetGridRow,
    decode_browse_cursor,
    encode_browse_cursor,
)


class AssetBrowseCursorTest(unittest.TestCase):
    def test_cursor_scope_includes_tag_ids(self) -> None:
        row = AssetGridRow(
            id=uuid4(),
            mime_type="image/jpeg",
            media_kind="image",
            width=100,
            height=100,
            duration_seconds=None,
            is_favorite=False,
            captured_at=None,
            timeline_at=datetime.now(timezone.utc),
            timeline_day=date(2026, 5, 23),
            blurhash=None,
            has_large_preview=False,
        )
        encoded = encode_browse_cursor(
            filters=AssetGridFilters(tag_ids=(1,)),
            row=row,
        )

        with self.assertRaises(HTTPException):
            decode_browse_cursor(
                encoded,
                filters=AssetGridFilters(tag_ids=(2,)),
            )


if __name__ == "__main__":
    unittest.main()
