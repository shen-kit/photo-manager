from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from app.services.embeddings.repository import (
    AssetEmbeddingSearchRow,
    EmbeddingRepository,
)
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError
from app.services.people.service import PeopleService


@dataclass(frozen=True)
class SearchResults:
    query: str
    items: list[AssetEmbeddingSearchRow]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class SearchCursor:
    scope: str
    distance: float | None = None
    timeline_at: datetime | None = None
    asset_id: UUID | None = None


def _scope(*, query: str, person_ids: list[UUID], tag_ids: list[int]) -> str:
    payload = {
        "query": query,
        "person_ids": [str(person_id) for person_id in person_ids],
        "tag_ids": tag_ids,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _encode_search_cursor(
    *,
    query: str,
    person_ids: list[UUID],
    tag_ids: list[int],
    row: AssetEmbeddingSearchRow,
) -> str:
    payload = {
        "v": 1,
        "scope": _scope(query=query, person_ids=person_ids, tag_ids=tag_ids),
        "distance": row.distance,
        "timeline_at": row.asset.timeline_at.isoformat(),
        "asset_id": str(row.asset.id),
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")


def _decode_search_cursor(
    cursor: str | None,
    *,
    query: str,
    person_ids: list[UUID],
    tag_ids: list[int],
) -> SearchCursor | None:
    if cursor is None:
        return None
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        )
        if int(payload["v"]) != 1:
            raise ValueError("Unsupported cursor version")
        scope = str(payload["scope"])
        distance = float(payload["distance"])
        timeline_at = datetime.fromisoformat(payload["timeline_at"])
        asset_id = UUID(payload["asset_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc
    expected_scope = _scope(query=query, person_ids=person_ids, tag_ids=tag_ids)
    if scope != expected_scope:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cursor does not match the requested filters",
        )
    return SearchCursor(
        scope=scope,
        distance=distance,
        timeline_at=timeline_at,
        asset_id=asset_id,
    )


class SearchService:
    def __init__(
        self,
        session: Session,
        *,
        embedding_service: EmbeddingService | None = None,
        embedding_repository: EmbeddingRepository | None = None,
        people_service: PeopleService | None = None,
    ) -> None:
        self.session = session
        self.embedding_service = embedding_service or EmbeddingService(session)
        self.embedding_repository = embedding_repository or EmbeddingRepository(session)
        self.people_service = people_service or PeopleService(session)

    def search(
        self,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
        person_ids: list[UUID] | None = None,
        tag_ids: list[int] | None = None,
    ) -> SearchResults:
        normalized = query.strip() if query else ""
        validated_person_ids = self.people_service.validate_person_ids(person_ids or [])
        normalized_tag_ids = list(dict.fromkeys(tag_ids or []))
        if not normalized and not validated_person_ids:
            raise EmbeddingServiceError(
                "Search query or person_ids filter must be provided"
            )
        parsed_cursor = _decode_search_cursor(
            cursor,
            query=normalized,
            person_ids=validated_person_ids,
            tag_ids=normalized_tag_ids,
        )

        if normalized:
            model_id, query_embedding = self.embedding_service.embed_text_query(
                normalized
            )
            items = self.embedding_repository.search_similar_assets(
                model_id=model_id,
                query_embedding=query_embedding,
                limit=limit + 1,
                cursor_distance=parsed_cursor.distance if parsed_cursor else None,
                cursor_timeline_at=parsed_cursor.timeline_at if parsed_cursor else None,
                cursor_asset_id=parsed_cursor.asset_id if parsed_cursor else None,
                person_ids=validated_person_ids,
                tag_ids=normalized_tag_ids,
            )
        else:
            items = self.embedding_repository.list_assets_for_people(
                person_ids=validated_person_ids,
                limit=limit + 1,
                cursor_timeline_at=parsed_cursor.timeline_at if parsed_cursor else None,
                cursor_asset_id=parsed_cursor.asset_id if parsed_cursor else None,
                tag_ids=normalized_tag_ids,
            )
        has_more = len(items) > limit
        page_items = items[:limit]
        next_cursor = None
        if has_more and page_items:
            next_cursor = _encode_search_cursor(
                query=normalized,
                person_ids=validated_person_ids,
                tag_ids=normalized_tag_ids,
                row=page_items[-1],
            )
        return SearchResults(
            query=normalized,
            items=page_items,
            next_cursor=next_cursor,
            has_more=has_more,
        )
