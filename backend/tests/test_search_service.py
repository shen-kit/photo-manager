from __future__ import annotations

import base64
import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models import Asset
from app.services.embeddings.repository import AssetEmbeddingSearchRow

sys.modules.setdefault("open_clip", SimpleNamespace())
sys.modules.setdefault(
    "torch",
    SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        nn=SimpleNamespace(Module=object),
        autocast=lambda *args, **kwargs: None,
        inference_mode=lambda: None,
        Tensor=object,
    ),
)

from app.services.search.service import SearchService


class _FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_text_query(self, query: str):
        self.calls.append(query)
        return 11, [0.1, 0.2]


class _FakeEmbeddingRepository:
    def __init__(self, rows: list[AssetEmbeddingSearchRow]) -> None:
        self.rows = rows
        self.count_calls = []
        self.search_calls = []
        self.people_count_calls = []
        self.people_list_calls = []

    def count_searchable_assets(
        self,
        *,
        model_id: int,
        person_ids: list | None = None,
        tag_ids: list | None = None,
    ):
        self.count_calls.append((model_id, person_ids, tag_ids))
        return len(self.rows)

    def search_similar_assets(
        self,
        *,
        model_id: int,
        query_embedding,
        limit: int,
        cursor_distance=None,
        cursor_timeline_at=None,
        cursor_asset_id=None,
        person_ids=None,
        tag_ids=None,
    ):
        self.search_calls.append(
            (
                model_id,
                query_embedding,
                limit,
                cursor_distance,
                cursor_timeline_at,
                cursor_asset_id,
                person_ids,
                tag_ids,
            )
        )
        return list(self.rows)

    def count_assets_for_people(self, *, person_ids):
        self.people_count_calls.append(person_ids)
        return len(self.rows)

    def list_assets_for_people(
        self,
        *,
        person_ids,
        limit: int,
        cursor_timeline_at=None,
        cursor_asset_id=None,
        tag_ids=None,
    ):
        self.people_list_calls.append(
            (person_ids, limit, cursor_timeline_at, cursor_asset_id, tag_ids)
        )
        return list(self.rows)


class _FakePeopleService:
    def __init__(self, validated_ids):
        self.validated_ids = validated_ids
        self.calls = []

    def validate_person_ids(self, person_ids):
        self.calls.append(list(person_ids))
        return list(self.validated_ids)


def _row() -> AssetEmbeddingSearchRow:
    asset = Asset(
        id=uuid4(),
        file_hash="hash",
        master_path="2026/05/a.jpg",
        mime_type="image/jpeg",
        has_large_preview=False,
        created_at=datetime.now(timezone.utc),
    )
    return AssetEmbeddingSearchRow(asset=asset, distance=0.25)


class SearchServiceTest(unittest.TestCase):
    def test_people_only_search_skips_text_embedding(self) -> None:
        rows = [_row()]
        embedding_service = _FakeEmbeddingService()
        embedding_repository = _FakeEmbeddingRepository(rows)
        person_ids = [uuid4()]
        service = SearchService(
            session=None,
            embedding_service=embedding_service,
            embedding_repository=embedding_repository,
            people_service=_FakePeopleService(person_ids),
        )

        result = service.search(
            query=None, limit=10, cursor=None, person_ids=person_ids
        )

        self.assertEqual(result.query, "")
        self.assertEqual(embedding_service.calls, [])
        self.assertEqual(
            embedding_repository.people_list_calls,
            [(person_ids, 11, None, None, [])],
        )

    def test_text_search_with_people_filters_passes_validated_ids(self) -> None:
        rows = [_row()]
        embedding_service = _FakeEmbeddingService()
        embedding_repository = _FakeEmbeddingRepository(rows)
        requested_ids = [uuid4(), uuid4(), uuid4()]
        validated_ids = [requested_ids[0], requested_ids[1]]
        people_service = _FakePeopleService(validated_ids)
        service = SearchService(
            session=None,
            embedding_service=embedding_service,
            embedding_repository=embedding_repository,
            people_service=people_service,
        )

        result = service.search(
            query="beach",
            limit=25,
            cursor=None,
            person_ids=requested_ids,
        )

        self.assertEqual(result.query, "beach")
        self.assertEqual(embedding_service.calls, ["beach"])
        self.assertEqual(people_service.calls, [requested_ids])
        self.assertEqual(
            embedding_repository.search_calls,
            [(11, [0.1, 0.2], 26, None, None, None, validated_ids, [])],
        )

    def test_requires_query_or_people_filter(self) -> None:
        service = SearchService(
            session=None,
            embedding_service=_FakeEmbeddingService(),
            embedding_repository=_FakeEmbeddingRepository([]),
            people_service=_FakePeopleService([]),
        )

        with self.assertRaises(RuntimeError):
            service.search(query=None, limit=10, cursor=None, person_ids=[])

    def test_cursor_scope_mismatch_is_rejected(self) -> None:
        rows = [_row()]
        service = SearchService(
            session=None,
            embedding_service=_FakeEmbeddingService(),
            embedding_repository=_FakeEmbeddingRepository(rows),
            people_service=_FakePeopleService([]),
        )
        payload = {
            "v": 1,
            "scope": "wrong",
            "distance": 0.25,
            "timeline_at": rows[0].asset.timeline_at.isoformat(),
            "asset_id": str(rows[0].asset.id),
        }
        cursor = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode(
            "utf-8"
        )

        with self.assertRaises(Exception):
            service.search(query="beach", limit=10, cursor=cursor, person_ids=[])


if __name__ == "__main__":
    unittest.main()
