from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, text
from sqlmodel import Session, select

from app.models import Asset, AssetTag, Face, Person, Tag


@dataclass(frozen=True)
class AssetEmbeddingSearchRow:
    asset: Asset
    tags: list[dict[str, Any]] | None
    faces: list[dict[str, Any]] | None
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

    def count_searchable_assets(self, *, model_id: int) -> int:
        rows = self.session.execute(
            text(
                """
                SELECT count(*)
                FROM assets
                WHERE deleted_at IS NULL
                  AND search_vector IS NOT NULL
                  AND search_model_id = :model_id
                """
            ),
            {"model_id": model_id},
        )
        return int(rows.scalar_one())

    def search_similar_assets(
        self,
        *,
        model_id: int,
        query_embedding: list[float],
        limit: int,
        offset: int,
    ) -> list[AssetEmbeddingSearchRow]:
        result = self.session.execute(
            text(
                """
                SELECT id, search_vector <=> CAST(:query_vector AS vector) AS distance
                FROM assets
                WHERE deleted_at IS NULL
                  AND search_vector IS NOT NULL
                  AND search_model_id = :model_id
                ORDER BY search_vector <=> CAST(:query_vector AS vector), created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "query_vector": vector_literal(query_embedding),
                "model_id": model_id,
                "limit": limit,
                "offset": offset,
            },
        )
        rows = result.fetchall()
        if not rows:
            return []

        asset_ids = [row.id for row in rows]
        distance_by_id = {row.id: float(row.distance) for row in rows}
        tags_subquery, faces_subquery = self._asset_relations_subqueries()
        ordering = case(
            {asset_id: index for index, asset_id in enumerate(asset_ids)},
            value=Asset.id,
        )
        statement = (
            select(Asset, tags_subquery.c.tags, faces_subquery.c.faces)
            .where(Asset.id.in_(asset_ids))
            .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
            .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
            .order_by(ordering)
        )
        hydrated_rows = self.session.exec(statement).all()
        return [
            AssetEmbeddingSearchRow(
                asset=asset,
                tags=tags,
                faces=faces,
                distance=distance_by_id[asset.id],
            )
            for asset, tags, faces in hydrated_rows
        ]

    def _asset_relations_subqueries(self) -> tuple[Any, Any]:
        tags_subquery = (
            select(
                AssetTag.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Tag.id,
                        "name",
                        Tag.name,
                        "path",
                        Tag.path,
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
            .group_by(Face.asset_id)
            .subquery()
        )
        return tags_subquery, faces_subquery
