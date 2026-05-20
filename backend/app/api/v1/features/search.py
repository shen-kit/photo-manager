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
    SearchFaceSummary,
    SearchPersonSummary,
    SearchResponse,
    SearchResultItem,
    SearchTagSummary,
)
from app.services.search.service import SearchService

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


def _thumbnail_url(request: Request, asset_id: UUID) -> str:
    return (
        str(request.base_url).rstrip("/")
        + f"/media/processed/assets/{asset_id}/small.webp"
    )


def _build_tag_models(rows: list[dict[str, object]] | None) -> list[SearchTagSummary]:
    return [SearchTagSummary.model_validate(row) for row in (rows or [])]


def _build_face_models(rows: list[dict[str, object]] | None) -> list[SearchFaceSummary]:
    items: list[SearchFaceSummary] = []
    for row in rows or []:
        person_id = row.get("person_id")
        person_name = row.get("person_name")
        items.append(
            SearchFaceSummary(
                id=row["id"],
                person=SearchPersonSummary(id=person_id, name=person_name)
                if person_id or person_name
                else None,
            )
        )
    return items


@router.get("", response_model=SearchResponse, include_in_schema=False)
@router.get("/", response_model=SearchResponse)
def search_assets(
    request: Request,
    query: str | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    limit: int = Query(default=SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    del current_user
    parsed_person_ids = _parse_person_ids(person_ids)
    try:
        results = SearchService(session).search(
            query=query,
            limit=limit,
            offset=offset,
            person_ids=parsed_person_ids,
        )
    except EmbeddingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    items = [
        SearchResultItem(
            id=row.asset.id,
            captured_at=row.asset.captured_at,
            description=row.asset.description,
            is_favorite=row.asset.is_favorite,
            width=row.asset.width,
            height=row.asset.height,
            has_large_preview=row.asset.has_large_preview,
            small_thumbnail_url=_thumbnail_url(request, row.asset.id),
            blurhash=row.asset.blurhash,
            distance=row.distance,
            score=max(0.0, 1.0 - row.distance),
            tags=_build_tag_models(row.tags),
            faces=_build_face_models(row.faces),
        )
        for row in results.items
    ]
    return SearchResponse(
        items=items,
        query=results.query,
        limit=results.limit,
        offset=results.offset,
        total=results.total,
    )
