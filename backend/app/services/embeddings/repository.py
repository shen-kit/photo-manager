from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, text
from sqlmodel import Session, select

from app.models import Asset, Face
from app.services.tags.filtering import matching_assets_by_tag_filters_subquery


@dataclass(frozen=True)
class AssetEmbeddingSearchRow:
    asset: Asset
    distance: float


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in values) + "]"


class EmbeddingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset(self, asset_id: UUID) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def asset_has_embedding(self, asset: Asset, model_id: int) -> bool:
        return asset.search_model_id == model_id and asset.search_vector is not None

    def upsert_asset_embedding(
        self,
        *,
        asset_id: UUID,
        model_id: int,
        embedding: list[float],
    ) -> None:
        self.session.execute(
            text(
                """
                UPDATE assets
                SET search_vector = CAST(:search_vector AS vector),
                    search_model_id = :search_model_id
                WHERE id = :asset_id
                """
            ),
            {
                "asset_id": asset_id,
                "search_model_id": model_id,
                "search_vector": vector_literal(embedding),
            },
        )
        self.session.commit()

    def count_assets_missing_embeddings(self, *, model_id: int, force: bool) -> int:
        statement = (
            select(func.count()).select_from(Asset).where(Asset.deleted_at.is_(None))
        )
        if not force:
            statement = statement.where(
                (Asset.search_vector.is_(None)) | (Asset.search_model_id != model_id)
            )
        return int(self.session.exec(statement).one())

    def list_asset_ids_missing_embeddings(
        self,
        *,
        model_id: int,
        force: bool,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UUID]:
        statement = (
            select(Asset.id)
            .where(Asset.deleted_at.is_(None))
            .order_by(Asset.created_at.asc())
            .offset(offset)
        )
        if not force:
            statement = statement.where(
                (Asset.search_vector.is_(None)) | (Asset.search_model_id != model_id)
            )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    def count_searchable_assets(
        self,
        *,
        model_id: int,
        person_ids: list[UUID] | None = None,
        tag_ids: list[int] | None = None,
    ) -> int:
        person_ids = person_ids or []
        tag_ids = tag_ids or []
        if not person_ids:
            statement = (
                select(func.count())
                .select_from(Asset)
                .where(
                    Asset.deleted_at.is_(None),
                    Asset.search_vector.is_not(None),
                    Asset.search_model_id == model_id,
                )
            )
            if tag_ids:
                matching_tags = matching_assets_by_tag_filters_subquery(tag_ids)
                if matching_tags is not None:
                    statement = statement.join(
                        matching_tags, matching_tags.c.asset_id == Asset.id
                    )
            return int(self.session.exec(statement).one())
        matching_assets = self._matching_assets_by_people_subquery(person_ids)
        statement = (
            select(func.count())
            .select_from(Asset)
            .join(matching_assets, matching_assets.c.asset_id == Asset.id)
            .where(
                Asset.deleted_at.is_(None),
                Asset.search_vector.is_not(None),
                Asset.search_model_id == model_id,
            )
        )
        if tag_ids:
            matching_tags = matching_assets_by_tag_filters_subquery(tag_ids)
            if matching_tags is not None:
                statement = statement.join(
                    matching_tags, matching_tags.c.asset_id == Asset.id
                )
        return int(self.session.exec(statement).one())

    def search_similar_assets(
        self,
        *,
        model_id: int,
        query_embedding: list[float],
        limit: int,
        cursor_distance: float | None = None,
        cursor_timeline_at: datetime | None = None,
        cursor_asset_id: UUID | None = None,
        person_ids: list[UUID] | None = None,
        tag_ids: list[int] | None = None,
    ) -> list[AssetEmbeddingSearchRow]:
        person_ids = person_ids or []
        tag_ids = tag_ids or []
        people_join = ""
        tag_join = ""
        where_clauses = [
            "deleted_at IS NULL",
            "search_vector IS NOT NULL",
            "search_model_id = :model_id",
        ]
        parameters: dict[str, object] = {
            "query_vector": vector_literal(query_embedding),
            "model_id": model_id,
            "limit": limit,
        }
        if person_ids:
            people_join = """
                JOIN (
                    SELECT asset_id
                    FROM faces
                    WHERE asset_id IS NOT NULL
                      AND is_excluded = false
                      AND person_id = ANY(CAST(:person_ids AS uuid[]))
                    GROUP BY asset_id
                    HAVING count(DISTINCT person_id) = :person_count
                ) AS matched_people ON matched_people.asset_id = assets.id
            """
            parameters["person_ids"] = person_ids
            parameters["person_count"] = len(person_ids)
        if tag_ids:
            tag_join = """
                JOIN (
                    SELECT asset_tags.asset_id
                    FROM asset_tags
                    JOIN tags assigned_tag ON assigned_tag.id = asset_tags.tag_id
                    JOIN tags selected_tag ON assigned_tag.path <@ selected_tag.path
                    WHERE selected_tag.id = ANY(CAST(:tag_ids AS integer[]))
                    GROUP BY asset_tags.asset_id
                    HAVING count(DISTINCT selected_tag.id) = :tag_count
                ) AS matched_tags ON matched_tags.asset_id = assets.id
            """
            parameters["tag_ids"] = tag_ids
            parameters["tag_count"] = len(tag_ids)
        if (
            cursor_distance is not None
            and cursor_timeline_at is not None
            and cursor_asset_id is not None
        ):
            where_clauses.append(
                """
                (
                    search_vector <=> CAST(:query_vector AS vector) > :cursor_distance
                    OR (
                        search_vector <=> CAST(:query_vector AS vector) = :cursor_distance
                        AND (
                            timeline_at < :cursor_timeline_at
                            OR (timeline_at = :cursor_timeline_at AND id < :cursor_asset_id)
                        )
                    )
                )
                """
            )
            parameters["cursor_distance"] = cursor_distance
            parameters["cursor_timeline_at"] = cursor_timeline_at
            parameters["cursor_asset_id"] = cursor_asset_id
        result = self.session.execute(
            text(
                f"""
                SELECT id, search_vector <=> CAST(:query_vector AS vector) AS distance
                FROM assets
                {people_join}
                {tag_join}
                WHERE {" AND ".join(where_clauses)}
                ORDER BY search_vector <=> CAST(:query_vector AS vector), timeline_at DESC, id DESC
                LIMIT :limit
                """
            ),
            parameters,
        )
        rows = result.fetchall()
        if not rows:
            return []

        asset_ids = [row.id for row in rows]
        distance_by_id = {row.id: float(row.distance) for row in rows}
        ordering = case(
            {asset_id: index for index, asset_id in enumerate(asset_ids)},
            value=Asset.id,
        )
        statement = select(Asset).where(Asset.id.in_(asset_ids)).order_by(ordering)
        hydrated_rows = self.session.exec(statement).all()
        return [
            AssetEmbeddingSearchRow(
                asset=asset,
                distance=distance_by_id[asset.id],
            )
            for asset in hydrated_rows
        ]

    def count_assets_for_people(self, *, person_ids: list[UUID]) -> int:
        matching_assets = self._matching_assets_by_people_subquery(person_ids)
        statement = select(func.count()).select_from(matching_assets)
        return int(self.session.exec(statement).one())

    def list_assets_for_people(
        self,
        *,
        person_ids: list[UUID],
        limit: int,
        cursor_timeline_at: datetime | None = None,
        cursor_asset_id: UUID | None = None,
        tag_ids: list[int] | None = None,
    ) -> list[AssetEmbeddingSearchRow]:
        matching_assets = self._matching_assets_by_people_subquery(person_ids)
        statement = (
            select(Asset.id)
            .join(matching_assets, matching_assets.c.asset_id == Asset.id)
            .where(Asset.deleted_at.is_(None))
        )
        if tag_ids:
            matching_tags = matching_assets_by_tag_filters_subquery(tag_ids)
            if matching_tags is not None:
                statement = statement.join(
                    matching_tags, matching_tags.c.asset_id == Asset.id
                )
        if cursor_timeline_at is not None and cursor_asset_id is not None:
            statement = statement.where(
                (Asset.timeline_at < cursor_timeline_at)
                | (
                    (Asset.timeline_at == cursor_timeline_at)
                    & (Asset.id < cursor_asset_id)
                )
            )
        ordered_asset_ids = list(
            self.session.exec(
                statement.order_by(Asset.timeline_at.desc(), Asset.id.desc()).limit(
                    limit
                )
            ).all()
        )
        if not ordered_asset_ids:
            return []
        distance_by_id = {asset_id: 0.0 for asset_id in ordered_asset_ids}
        ordering = case(
            {asset_id: index for index, asset_id in enumerate(ordered_asset_ids)},
            value=Asset.id,
        )
        hydrated_rows = self.session.exec(
            select(Asset).where(Asset.id.in_(ordered_asset_ids)).order_by(ordering)
        ).all()
        return [
            AssetEmbeddingSearchRow(
                asset=asset,
                distance=distance_by_id[asset.id],
            )
            for asset in hydrated_rows
        ]

    def _matching_assets_by_people_subquery(self, person_ids: list[UUID]):
        return (
            select(Face.asset_id.label("asset_id"))
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Asset.deleted_at.is_(None),
                Face.asset_id.is_not(None),
                Face.is_excluded.is_(False),
                Face.person_id.in_(person_ids),
            )
            .group_by(Face.asset_id)
            .having(func.count(func.distinct(Face.person_id)) == len(person_ids))
            .subquery()
        )
