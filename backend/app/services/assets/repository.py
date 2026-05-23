from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Asset, AssetTag, Face, Person, Tag


TrashAssetSort = Literal[
    "deleted_at_desc",
    "deleted_at_asc",
    "taken_at_desc",
    "taken_at_asc",
]


def active_asset_where():
    return Asset.deleted_at.is_(None)


def deleted_asset_where():
    return Asset.deleted_at.is_not(None)


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_asset(self, asset_id: UUID) -> Asset | None:
        statement = select(Asset).where(Asset.id == asset_id, active_asset_where())
        return self.session.exec(statement).first()

    def get_deleted_asset(self, asset_id: UUID) -> Asset | None:
        statement = select(Asset).where(Asset.id == asset_id, deleted_asset_where())
        return self.session.exec(statement).first()

    def get_active_asset_detail(
        self, asset_id: UUID
    ) -> tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None] | None:
        rows = self._list_assets_hydrated(
            where_clauses=[Asset.id == asset_id, active_asset_where()],
            limit=1,
        )
        return rows[0] if rows else None

    def get_deleted_asset_detail(
        self, asset_id: UUID
    ) -> tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None] | None:
        rows = self._list_assets_hydrated(
            where_clauses=[Asset.id == asset_id, deleted_asset_where()],
            limit=1,
        )
        return rows[0] if rows else None

    def count_deleted_assets(self) -> int:
        statement = select(func.count()).select_from(Asset).where(deleted_asset_where())
        return int(self.session.exec(statement).one())

    def list_deleted_assets(
        self,
        *,
        limit: int,
        offset: int,
        sort: TrashAssetSort,
    ) -> list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]:
        if sort == "deleted_at_desc":
            order_by = [
                Asset.deleted_at.desc(),
                Asset.created_at.desc(),
                Asset.id.desc(),
            ]
        elif sort == "deleted_at_asc":
            order_by = [Asset.deleted_at.asc(), Asset.created_at.asc(), Asset.id.asc()]
        elif sort == "taken_at_asc":
            order_by = [
                Asset.captured_at.asc().nullslast(),
                Asset.created_at.asc(),
                Asset.id.asc(),
            ]
        else:
            order_by = [
                Asset.captured_at.desc().nullslast(),
                Asset.created_at.desc(),
                Asset.id.desc(),
            ]
        return self._list_assets_hydrated(
            where_clauses=[deleted_asset_where()],
            order_by=order_by,
            limit=limit,
            offset=offset,
        )

    def restore_deleted_asset(self, asset: Asset) -> Asset:
        asset.deleted_at = None
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def list_person_ids_for_asset(self, *, asset_id: UUID) -> list[UUID]:
        statement = select(func.distinct(Face.person_id)).where(
            Face.asset_id == asset_id, Face.person_id.is_not(None)
        )
        return [
            person_id for person_id in self.session.exec(statement).all() if person_id
        ]

    def _list_assets_hydrated(
        self,
        *,
        where_clauses: list[object],
        order_by: list[object] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]:
        tags_subquery, faces_subquery = self._asset_relations_subqueries()
        statement = (
            select(
                Asset,
                tags_subquery.c.tags,
                faces_subquery.c.faces,
            )
            .where(*where_clauses)
            .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
            .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
            .offset(offset)
        )
        if order_by:
            statement = statement.order_by(*order_by)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    @staticmethod
    def _asset_relations_subqueries() -> tuple[Any, Any]:
        tags_subquery = (
            select(
                AssetTag.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Tag.id,
                        "name",
                        Tag.name,
                        "slug",
                        Tag.slug,
                        "path",
                        Tag.path,
                        "is_album",
                        Tag.is_album,
                        "cover_asset_id",
                        Tag.cover_asset_id,
                    )
                ).label("tags"),
            )
            .select_from(AssetTag)
            .join(Tag, Tag.id == AssetTag.tag_id)
            .group_by(AssetTag.asset_id)
            .subquery()
        )

        faces_subquery = (
            select(
                Face.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Face.id,
                        "person_id",
                        Person.id,
                        "person_name",
                        Person.name,
                    )
                ).label("faces"),
            )
            .select_from(Face)
            .join(Person, Person.id == Face.person_id, isouter=True)
            .where(Face.is_excluded.is_(False))
            .group_by(Face.asset_id)
            .subquery()
        )

        return tags_subquery, faces_subquery
