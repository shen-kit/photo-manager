from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models import User
from app.services.embeddings.service import (
    EmbeddingServiceError,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
)
from app.services.search.schemas import (
    SearchResponse,
    SearchResultItem,
)
from app.services.search.service import SearchService
from app.services.tags.service import TagService, get_tag_service

router = APIRouter()


def _parse_person_ids(raw_person_ids: str | None) -> list[UUID]:
    if raw_person_ids is None or not raw_person_ids.strip():
        return []
    values: list[UUID] = []
    for item in raw_person_ids.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            values.append(UUID(normalized))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="person_ids must be a comma-separated list of UUIDs",
            ) from exc
    return values


def _parse_tag_ids(raw_tag_ids: str | None) -> list[int]:
    if raw_tag_ids is None or not raw_tag_ids.strip():
        return []
    values: list[int] = []
    for item in raw_tag_ids.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            values.append(int(normalized))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tag_ids must be a comma-separated list of integers",
            ) from exc
    return list(dict.fromkeys(values))


def _thumbnail_url(request: Request, asset_id: UUID) -> str:
    return (
        str(request.base_url).rstrip("/")
        + f"/media/processed/assets/{asset_id}/small.webp"
    )


@router.get("", response_model=SearchResponse, include_in_schema=False)
@router.get("/", response_model=SearchResponse)
def search_assets(
    request: Request,
    query: str | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    tag_ids: str | None = Query(default=None),
    limit: int = Query(default=SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_session),
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    del current_user
    parsed_person_ids = _parse_person_ids(person_ids)
    parsed_tag_ids = tag_service.validate_tag_ids(_parse_tag_ids(tag_ids))
    try:
        results = SearchService(session).search(
            query=query,
            limit=limit,
            cursor=cursor,
            person_ids=parsed_person_ids,
            tag_ids=parsed_tag_ids,
        )
    except EmbeddingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    items = [
        SearchResultItem(
            id=row.asset.id,
            mime_type=row.asset.mime_type,
            media_kind=row.asset.media_kind,
            captured_at=row.asset.captured_at,
            timeline_day=row.asset.timeline_day,
            is_favorite=row.asset.is_favorite,
            width=row.asset.width,
            height=row.asset.height,
            duration_seconds=row.asset.duration_seconds,
            has_large_preview=row.asset.has_large_preview,
            small_thumbnail_url=_thumbnail_url(request, row.asset.id),
            blurhash=row.asset.blurhash,
            distance=row.distance,
            score=max(0.0, 1.0 - row.distance),
        )
        for row in results.items
    ]
    return SearchResponse(
        items=items,
        query=results.query,
        next_cursor=results.next_cursor,
        has_more=results.has_more,
    )
