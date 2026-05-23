from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.models import Asset, AssetTag, Tag


class TagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_tag(self, tag_id: int) -> Tag | None:
        return self.session.get(Tag, tag_id)

    def list_tags(
        self,
        *,
        is_album: bool | None = None,
        parent_path: str | None = None,
        subtree_path: str | None = None,
    ) -> list[Tag]:
        statement = select(Tag)
        if is_album is not None:
            statement = statement.where(Tag.is_album == is_album)
        if parent_path is not None:
            statement = statement.where(
                func.subpath(Tag.path, 0, func.nlevel(Tag.path) - 1) == parent_path
            )
        if subtree_path is not None:
            statement = statement.where(Tag.path.op("<@")(subtree_path))
        return list(self.session.exec(statement.order_by(Tag.path.asc())).all())

    def list_existing_tag_ids(self, tag_ids: list[int]) -> list[int]:
        if not tag_ids:
            return []
        statement = select(Tag.id).where(Tag.id.in_(tag_ids))
        return list(self.session.exec(statement).all())

    def list_existing_asset_ids(self, asset_ids: list[UUID]) -> list[UUID]:
        if not asset_ids:
            return []
        statement = select(Asset.id).where(
            Asset.id.in_(asset_ids), Asset.deleted_at.is_(None)
        )
        return list(self.session.exec(statement).all())

    def create_tag(self, tag: Tag) -> Tag:
        self.session.add(tag)
        self.session.commit()
        self.session.refresh(tag)
        return tag

    def save_tag(self, tag: Tag) -> Tag:
        self.session.add(tag)
        self.session.commit()
        self.session.refresh(tag)
        return tag

    def path_exists(self, path: str, *, exclude_tag_id: int | None = None) -> bool:
        statement = select(Tag.id).where(Tag.path == path)
        if exclude_tag_id is not None:
            statement = statement.where(Tag.id != exclude_tag_id)
        return self.session.exec(statement.limit(1)).first() is not None

    def count_descendants(self, tag_path: str) -> int:
        rows = self.session.execute(
            text(
                """
                SELECT count(*)
                FROM tags
                WHERE path <@ CAST(:tag_path AS ltree)
                  AND path != CAST(:tag_path AS ltree)
                """
            ),
            {"tag_path": tag_path},
        )
        return int(rows.scalar_one())

    def update_descendant_paths(self, *, old_path: str, new_path: str) -> None:
        self.session.execute(
            text(
                """
                UPDATE tags
                SET path = CAST(
                    text2ltree(:new_path)
                    || subpath(path, nlevel(text2ltree(:old_path)))
                    AS ltree
                ),
                    updated_at = now()
                WHERE path <@ text2ltree(:old_path)
                  AND path != text2ltree(:old_path)
                """
            ),
            {"old_path": old_path, "new_path": new_path},
        )

    def delete_tag_subtree(self, *, tag_path: str) -> None:
        self.session.execute(
            text("DELETE FROM tags WHERE path <@ text2ltree(:tag_path)"),
            {"tag_path": tag_path},
        )
        self.session.commit()

    def asset_belongs_to_tag_subtree(self, *, asset_id: UUID, tag_path: str) -> bool:
        rows = self.session.execute(
            text(
                """
                SELECT 1
                FROM asset_tags
                JOIN tags assigned_tag ON assigned_tag.id = asset_tags.tag_id
                WHERE asset_tags.asset_id = :asset_id
                  AND assigned_tag.path <@ text2ltree(:tag_path)
                LIMIT 1
                """
            ),
            {"asset_id": asset_id, "tag_path": tag_path},
        )
        return rows.first() is not None

    def add_tag_to_asset(self, *, asset_id: UUID, tag_id: int) -> None:
        statement = insert(AssetTag).values(asset_id=asset_id, tag_id=tag_id)
        statement = statement.on_conflict_do_nothing(
            index_elements=["asset_id", "tag_id"]
        )
        self.session.execute(statement)
        self.session.commit()

    def remove_tag_from_asset(self, *, asset_id: UUID, tag_id: int) -> None:
        asset_tag = self.session.get(AssetTag, (asset_id, tag_id))
        if asset_tag is not None:
            self.session.delete(asset_tag)
            self.session.commit()

    def batch_add_tags(self, *, asset_ids: list[UUID], tag_ids: list[int]) -> int:
        rows = [
            {"asset_id": asset_id, "tag_id": tag_id}
            for asset_id in asset_ids
            for tag_id in tag_ids
        ]
        if not rows:
            return 0
        statement = insert(AssetTag).values(rows)
        statement = statement.on_conflict_do_nothing(
            index_elements=["asset_id", "tag_id"]
        )
        result = self.session.execute(statement)
        self.session.commit()
        return result.rowcount or 0

    def batch_remove_tags(self, *, asset_ids: list[UUID], tag_ids: list[int]) -> int:
        if not asset_ids or not tag_ids:
            return 0
        result = self.session.execute(
            text(
                """
                DELETE FROM asset_tags
                WHERE asset_id = ANY(CAST(:asset_ids AS uuid[]))
                  AND tag_id = ANY(CAST(:tag_ids AS integer[]))
                """
            ),
            {"asset_ids": asset_ids, "tag_ids": tag_ids},
        )
        self.session.commit()
        return result.rowcount or 0

    def build_delete_conflict_detail(
        self, *, tag: Tag, descendant_count: int
    ) -> dict[str, Any]:
        return {
            "code": "tag_has_children",
            "tag_id": tag.id,
            "path": tag.path,
            "descendant_count": descendant_count,
            "delete_children_required": True,
        }
