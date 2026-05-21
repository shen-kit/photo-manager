from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import SQLModel

from app.core.auth import get_current_user
from app.models import User
from app.services.assets.browse import (
    AssetBrowseService,
    AssetGridFilters,
    TimelineBucketCover,
    get_asset_browse_service,
)
from app.services.people.service import PeopleService, get_people_service

router = APIRouter()


class TimelineBucketCoverResponse(SQLModel):
    id: UUID
    media_kind: str
    small_thumbnail_url: str
    blurhash: str | None = None


class TimelineMonthBucketResponse(SQLModel):
    month: date
    asset_count: int
    first_timeline_at: datetime
    last_timeline_at: datetime
    cover: TimelineBucketCoverResponse | None = None


class TimelineDayBucketResponse(SQLModel):
    day: date
    asset_count: int
    first_timeline_at: datetime
    last_timeline_at: datetime
    cover: TimelineBucketCoverResponse | None = None


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return (
        str(request.base_url).rstrip("/")
        + f"/media/processed/assets/{asset_id}/{variant}.webp"
    )


def _parse_person_ids(raw_person_ids: str | None) -> tuple[UUID, ...]:
    if raw_person_ids is None or not raw_person_ids.strip():
        return ()
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
    return tuple(dict.fromkeys(values))


def _build_timeline_cover(
    request: Request,
    cover: TimelineBucketCover | None,
) -> TimelineBucketCoverResponse | None:
    if cover is None:
        return None
    return TimelineBucketCoverResponse(
        id=cover.id,
        media_kind=cover.media_kind,
        small_thumbnail_url=_thumbnail_url(request, cover.id, "small"),
        blurhash=cover.blurhash,
    )


@router.get("/timeline/months", response_model=list[TimelineMonthBucketResponse])
def list_timeline_months(
    request: Request,
    media_kind: str | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    browse_service: AssetBrowseService = Depends(get_asset_browse_service),
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> list[TimelineMonthBucketResponse]:
    del current_user
    filters = AssetGridFilters(
        media_kind=media_kind,
        person_ids=tuple(
            people_service.validate_person_ids(list(_parse_person_ids(person_ids)))
        ),
    )
    buckets = browse_service.list_timeline_months(filters=filters)
    return [
        TimelineMonthBucketResponse(
            month=bucket.month,
            asset_count=bucket.asset_count,
            first_timeline_at=bucket.first_timeline_at,
            last_timeline_at=bucket.last_timeline_at,
            cover=_build_timeline_cover(request, bucket.cover),
        )
        for bucket in buckets
    ]


@router.get("/timeline/days", response_model=list[TimelineDayBucketResponse])
def list_timeline_days(
    request: Request,
    month: date = Query(...),
    media_kind: str | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    browse_service: AssetBrowseService = Depends(get_asset_browse_service),
    people_service: PeopleService = Depends(get_people_service),
    current_user: User = Depends(get_current_user),
) -> list[TimelineDayBucketResponse]:
    del current_user
    filters = AssetGridFilters(
        media_kind=media_kind,
        person_ids=tuple(
            people_service.validate_person_ids(list(_parse_person_ids(person_ids)))
        ),
    )
    buckets = browse_service.list_timeline_days(filters=filters, month=month)
    return [
        TimelineDayBucketResponse(
            day=bucket.day,
            asset_count=bucket.asset_count,
            first_timeline_at=bucket.first_timeline_at,
            last_timeline_at=bucket.last_timeline_at,
            cover=_build_timeline_cover(request, bucket.cover),
        )
        for bucket in buckets
    ]
