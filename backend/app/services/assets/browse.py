from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from fastapi import Depends
from sqlalchemy import Select, and_, func, or_, select
from sqlmodel import Session

from app.core.database import get_session
from app.models import Asset, Face
from app.services.tags.filtering import matching_assets_by_tag_filters_subquery

DEFAULT_GRID_LIMIT = 100
MAX_GRID_LIMIT = 200
CURSOR_VERSION = 1


@dataclass(frozen=True)
class AssetGridFilters:
    media_kind: str | None = None
    month: date | None = None
    day: date | None = None
    person_ids: tuple[UUID, ...] = ()
    tag_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class AssetGridRow:
    id: UUID
    mime_type: str
    media_kind: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    is_favorite: bool
    captured_at: datetime | None
    timeline_at: datetime
    timeline_day: date
    blurhash: str | None
    has_large_preview: bool


@dataclass(frozen=True)
class AssetGridPage:
    items: list[AssetGridRow]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class TimelineBucketCover:
    id: UUID
    media_kind: str
    blurhash: str | None


@dataclass(frozen=True)
class TimelineMonthBucket:
    month: date
    asset_count: int
    first_timeline_at: datetime
    last_timeline_at: datetime
    cover: TimelineBucketCover | None


@dataclass(frozen=True)
class TimelineDayBucket:
    day: date
    asset_count: int
    first_timeline_at: datetime
    last_timeline_at: datetime
    cover: TimelineBucketCover | None


@dataclass(frozen=True)
class _BrowseCursor:
    timeline_at: datetime
    asset_id: UUID
    scope: str


def _cursor_scope(filters: AssetGridFilters) -> str:
    payload = {
        "media_kind": filters.media_kind,
        "month": filters.month.isoformat() if filters.month else None,
        "day": filters.day.isoformat() if filters.day else None,
        "person_ids": [str(person_id) for person_id in filters.person_ids],
        "tag_ids": list(filters.tag_ids),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def encode_browse_cursor(*, filters: AssetGridFilters, row: AssetGridRow) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "sort": "timeline_desc",
        "timeline_at": row.timeline_at.isoformat(),
        "asset_id": str(row.id),
        "scope": _cursor_scope(filters),
    }
    return base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")


def decode_browse_cursor(
    cursor: str | None,
    *,
    filters: AssetGridFilters,
) -> _BrowseCursor | None:
    if cursor is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        version = int(payload["v"])
        if version != CURSOR_VERSION:
            raise ValueError("Unsupported cursor version")
        if payload.get("sort") != "timeline_desc":
            raise ValueError("Unsupported cursor sort")
        timeline_at = datetime.fromisoformat(payload["timeline_at"])
        asset_id = UUID(payload["asset_id"])
        scope = str(payload["scope"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc
    expected_scope = _cursor_scope(filters)
    if scope != expected_scope:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cursor does not match the requested filters",
        )
    return _BrowseCursor(timeline_at=timeline_at, asset_id=asset_id, scope=scope)


class AssetBrowseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_asset_grid_page(
        self,
        *,
        filters: AssetGridFilters,
        limit: int,
        cursor: _BrowseCursor | None,
    ) -> AssetGridPage:
        matching_assets = self._filtered_assets_query(filters)
        statement = (
            select(
                Asset.id,
                Asset.mime_type,
                Asset.media_kind,
                Asset.width,
                Asset.height,
                Asset.duration_seconds,
                Asset.is_favorite,
                Asset.captured_at,
                Asset.timeline_at,
                Asset.timeline_day,
                Asset.blurhash,
                Asset.has_large_preview,
            )
            .select_from(Asset)
            .join(matching_assets, matching_assets.c.id == Asset.id)
        )
        if cursor is not None:
            statement = statement.where(
                or_(
                    Asset.timeline_at < cursor.timeline_at,
                    and_(
                        Asset.timeline_at == cursor.timeline_at,
                        Asset.id < cursor.asset_id,
                    ),
                )
            )
        rows = list(
            self.session.exec(
                statement.order_by(Asset.timeline_at.desc(), Asset.id.desc()).limit(
                    limit + 1
                )
            ).all()
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [
            AssetGridRow(
                id=row.id,
                mime_type=row.mime_type,
                media_kind=row.media_kind,
                width=row.width,
                height=row.height,
                duration_seconds=row.duration_seconds,
                is_favorite=row.is_favorite,
                captured_at=row.captured_at,
                timeline_at=row.timeline_at,
                timeline_day=row.timeline_day,
                blurhash=row.blurhash,
                has_large_preview=row.has_large_preview,
            )
            for row in page_rows
        ]
        next_cursor = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            next_cursor = encode_browse_cursor(filters=filters, row=last_row)
        return AssetGridPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def list_timeline_months(
        self,
        *,
        filters: AssetGridFilters,
    ) -> list[TimelineMonthBucket]:
        return self._list_timeline_buckets(filters=filters, bucket_kind="month")

    def list_timeline_days(
        self,
        *,
        filters: AssetGridFilters,
        month: date,
    ) -> list[TimelineDayBucket]:
        day_filters = AssetGridFilters(
            media_kind=filters.media_kind,
            month=month,
            day=None,
            person_ids=filters.person_ids,
        )
        return self._list_timeline_buckets(filters=day_filters, bucket_kind="day")

    def _list_timeline_buckets(
        self,
        *,
        filters: AssetGridFilters,
        bucket_kind: str,
    ) -> list[TimelineMonthBucket] | list[TimelineDayBucket]:
        matching_assets = self._filtered_assets_query(filters)
        bucket_column = (
            Asset.timeline_month if bucket_kind == "month" else Asset.timeline_day
        )
        ranked = (
            select(
                Asset.id.label("asset_id"),
                Asset.media_kind.label("media_kind"),
                Asset.blurhash.label("blurhash"),
                Asset.timeline_at.label("timeline_at"),
                bucket_column.label("bucket"),
                func.row_number()
                .over(
                    partition_by=bucket_column,
                    order_by=(Asset.timeline_at.desc(), Asset.id.desc()),
                )
                .label("bucket_rank"),
            )
            .select_from(Asset)
            .join(matching_assets, matching_assets.c.id == Asset.id)
            .subquery()
        )
        aggregated = (
            select(
                bucket_column.label("bucket"),
                func.count().label("asset_count"),
                func.max(Asset.timeline_at).label("first_timeline_at"),
                func.min(Asset.timeline_at).label("last_timeline_at"),
            )
            .select_from(Asset)
            .join(matching_assets, matching_assets.c.id == Asset.id)
            .group_by(bucket_column)
            .subquery()
        )
        cover_rows = ranked.alias("cover_rows")
        statement = (
            select(
                aggregated.c.bucket,
                aggregated.c.asset_count,
                aggregated.c.first_timeline_at,
                aggregated.c.last_timeline_at,
                cover_rows.c.asset_id,
                cover_rows.c.media_kind,
                cover_rows.c.blurhash,
            )
            .select_from(aggregated)
            .outerjoin(
                cover_rows,
                and_(
                    cover_rows.c.bucket == aggregated.c.bucket,
                    cover_rows.c.bucket_rank == 1,
                ),
            )
            .order_by(aggregated.c.bucket.desc())
        )
        rows = list(self.session.exec(statement).all())
        if bucket_kind == "month":
            return [
                TimelineMonthBucket(
                    month=row.bucket,
                    asset_count=int(row.asset_count),
                    first_timeline_at=row.first_timeline_at,
                    last_timeline_at=row.last_timeline_at,
                    cover=TimelineBucketCover(
                        id=row.asset_id,
                        media_kind=row.media_kind,
                        blurhash=row.blurhash,
                    )
                    if row.asset_id is not None
                    else None,
                )
                for row in rows
            ]
        return [
            TimelineDayBucket(
                day=row.bucket,
                asset_count=int(row.asset_count),
                first_timeline_at=row.first_timeline_at,
                last_timeline_at=row.last_timeline_at,
                cover=TimelineBucketCover(
                    id=row.asset_id,
                    media_kind=row.media_kind,
                    blurhash=row.blurhash,
                )
                if row.asset_id is not None
                else None,
            )
            for row in rows
        ]

    def _filtered_assets_query(self, filters: AssetGridFilters):
        statement: Select[tuple[UUID]] = select(Asset.id).where(
            Asset.deleted_at.is_(None)
        )
        if filters.media_kind is not None:
            statement = statement.where(Asset.media_kind == filters.media_kind)
        if filters.month is not None:
            statement = statement.where(Asset.timeline_month == filters.month)
        if filters.day is not None:
            statement = statement.where(Asset.timeline_day == filters.day)
        if filters.person_ids:
            matched_people = (
                select(Face.asset_id.label("asset_id"))
                .join(Asset, Asset.id == Face.asset_id)
                .where(
                    Asset.deleted_at.is_(None),
                    Face.asset_id.is_not(None),
                    Face.is_excluded.is_(False),
                    Face.person_id.in_(filters.person_ids),
                )
                .group_by(Face.asset_id)
                .having(
                    func.count(func.distinct(Face.person_id)) == len(filters.person_ids)
                )
                .subquery()
            )
            statement = statement.join(
                matched_people, matched_people.c.asset_id == Asset.id
            )
        if filters.tag_ids:
            matched_tags = matching_assets_by_tag_filters_subquery(filters.tag_ids)
            if matched_tags is not None:
                statement = statement.join(
                    matched_tags, matched_tags.c.asset_id == Asset.id
                )
        return statement.subquery()


class AssetBrowseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AssetBrowseRepository(session)

    def list_asset_grid_page(
        self,
        *,
        filters: AssetGridFilters,
        limit: int,
        cursor: str | None,
    ) -> AssetGridPage:
        self._validate_filters(filters)
        validated_limit = self._validate_limit(limit)
        return self.repository.list_asset_grid_page(
            filters=filters,
            limit=validated_limit,
            cursor=decode_browse_cursor(cursor, filters=filters),
        )

    def list_timeline_months(
        self,
        *,
        filters: AssetGridFilters,
    ) -> list[TimelineMonthBucket]:
        self._validate_filters(filters)
        return self.repository.list_timeline_months(filters=filters)

    def list_timeline_days(
        self,
        *,
        filters: AssetGridFilters,
        month: date,
    ) -> list[TimelineDayBucket]:
        if month.day != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="month must be the first day of a month",
            )
        month_filters = AssetGridFilters(
            media_kind=filters.media_kind,
            month=month,
            day=None,
            person_ids=filters.person_ids,
        )
        self._validate_filters(month_filters)
        return self.repository.list_timeline_days(filters=filters, month=month)

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if limit < 1 or limit > MAX_GRID_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"limit must be between 1 and {MAX_GRID_LIMIT}",
            )
        return limit

    @staticmethod
    def _validate_filters(filters: AssetGridFilters) -> None:
        if filters.media_kind not in {None, "image", "video"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="media_kind must be image or video",
            )
        if filters.month is not None and filters.month.day != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="month must be the first day of a month",
            )
        if filters.month is not None and filters.day is not None:
            if filters.day.replace(day=1) != filters.month:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="day must fall within the requested month",
                )


def get_asset_browse_service(
    session: Session = Depends(get_session),
) -> AssetBrowseService:
    return AssetBrowseService(session)
