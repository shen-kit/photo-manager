from __future__ import annotations

import re
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.models import Tag
from app.services.tags.repository import TagRepository


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _parent_path(path: str) -> str | None:
    if "." not in path:
        return None
    return path.rsplit(".", 1)[0]


def slugify_tag_name(name: str) -> str:
    slug = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tag name must produce a non-empty slug",
        )
    return slug


class TagService:
    def __init__(
        self,
        session: Session,
        *,
        repository: TagRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or TagRepository(session)

    def list_tags(
        self,
        *,
        is_album: bool | None = None,
        parent_id: int | None = None,
        subtree_id: int | None = None,
    ) -> list[Tag]:
        parent_path = None
        if parent_id is not None:
            parent = self.get_tag(parent_id, is_album=is_album)
            parent_path = parent.path
        subtree_path = None
        if subtree_id is not None:
            subtree_path = self.get_tag(subtree_id, is_album=is_album).path
        return self.repository.list_tags(
            is_album=is_album,
            parent_path=parent_path,
            subtree_path=subtree_path,
        )

    def get_tag(self, tag_id: int, *, is_album: bool | None = None) -> Tag:
        tag = self.repository.get_tag(tag_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        if is_album is not None and tag.is_album != is_album:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        return tag

    def create_tag(
        self,
        *,
        name: str,
        is_album: bool,
        parent_id: int | None = None,
        description: str | None = None,
        cover_asset_id: UUID | None = None,
        slug: str | None = None,
    ) -> Tag:
        normalized_slug = slugify_tag_name(slug or name)
        parent_path = None
        if parent_id is not None:
            parent = self.get_tag(parent_id)
            parent_path = parent.path
        path = (
            normalized_slug
            if parent_path is None
            else f"{parent_path}.{normalized_slug}"
        )
        if self.repository.path_exists(path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tag path already exists",
            )
        tag = Tag(
            name=name.strip(),
            slug=normalized_slug,
            path=path,
            is_album=is_album,
            description=description,
            cover_asset_id=None,
        )
        created = self.repository.create_tag(tag)
        if cover_asset_id is not None:
            created.cover_asset_id = self._validate_cover_asset(
                tag=created, cover_asset_id=cover_asset_id
            )
            created = self.repository.save_tag(created)
        return created

    def update_tag(
        self,
        tag_id: int,
        *,
        is_album: bool | None = None,
        name: str | None = None,
        parent_id: int | None = None,
        set_parent: bool = False,
        description: str | None = None,
        clear_description: bool = False,
        cover_asset_id: UUID | None = None,
        clear_cover: bool = False,
    ) -> Tag:
        tag = self.get_tag(tag_id, is_album=is_album)
        old_path = tag.path
        new_slug = tag.slug
        if name is not None:
            tag.name = name.strip()
            new_slug = slugify_tag_name(tag.name)
        parent_path = _parent_path(tag.path)
        if set_parent:
            parent_path = None
        if set_parent and parent_id is not None:
            if tag_id == parent_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Tag cannot be moved under itself",
                )
            parent = self.get_tag(parent_id)
            if parent.path == old_path or parent.path.startswith(old_path + "."):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Tag cannot be moved under its descendant",
                )
            parent_path = parent.path
        new_path = new_slug if parent_path is None else f"{parent_path}.{new_slug}"
        if self.repository.path_exists(new_path, exclude_tag_id=tag.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tag path already exists",
            )
        tag.slug = new_slug
        tag.path = new_path
        if clear_description:
            tag.description = None
        elif description is not None:
            tag.description = description
        if clear_cover:
            tag.cover_asset_id = None
        elif cover_asset_id is not None:
            tag.cover_asset_id = self._validate_cover_asset(
                tag=tag, cover_asset_id=cover_asset_id
            )
        if old_path != new_path:
            self.repository.update_descendant_paths(
                old_path=old_path, new_path=new_path
            )
        return self.repository.save_tag(tag)

    def delete_tag(
        self,
        tag_id: int,
        *,
        is_album: bool | None = None,
        delete_children: bool = False,
    ) -> None:
        tag = self.get_tag(tag_id, is_album=is_album)
        descendant_count = self.repository.count_descendants(tag.path)
        if descendant_count and not delete_children:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=self.repository.build_delete_conflict_detail(
                    tag=tag, descendant_count=descendant_count
                ),
            )
        self.repository.delete_tag_subtree(tag_path=tag.path)

    def validate_tag_ids(
        self,
        tag_ids: list[int],
        *,
        is_album: bool | None = None,
    ) -> list[int]:
        unique_ids = list(dict.fromkeys(tag_ids))
        if not unique_ids:
            return []
        existing = set(self.repository.list_existing_tag_ids(unique_ids))
        missing = [tag_id for tag_id in unique_ids if tag_id not in existing]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown tag ids: {', '.join(str(tag_id) for tag_id in missing)}",
            )
        if is_album is not None:
            for tag_id in unique_ids:
                tag = self.get_tag(tag_id)
                if tag.is_album != is_album:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Tag {tag_id} has incorrect album type",
                    )
        return unique_ids

    def validate_asset_ids(self, asset_ids: list[UUID]) -> list[UUID]:
        unique_ids = list(dict.fromkeys(asset_ids))
        existing = set(self.repository.list_existing_asset_ids(unique_ids))
        missing = [asset_id for asset_id in unique_ids if asset_id not in existing]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="One or more asset_ids do not exist",
            )
        return unique_ids

    def add_tag_to_asset(self, *, asset_id: UUID, tag_id: int) -> None:
        self.validate_asset_ids([asset_id])
        self.validate_tag_ids([tag_id])
        self.repository.add_tag_to_asset(asset_id=asset_id, tag_id=tag_id)

    def remove_tag_from_asset(self, *, asset_id: UUID, tag_id: int) -> None:
        self.validate_asset_ids([asset_id])
        self.validate_tag_ids([tag_id])
        self.repository.remove_tag_from_asset(asset_id=asset_id, tag_id=tag_id)

    def batch_add_tags(self, *, asset_ids: list[UUID], tag_ids: list[int]) -> int:
        validated_asset_ids = self.validate_asset_ids(asset_ids)
        validated_tag_ids = self.validate_tag_ids(tag_ids)
        return self.repository.batch_add_tags(
            asset_ids=validated_asset_ids,
            tag_ids=validated_tag_ids,
        )

    def batch_remove_tags(self, *, asset_ids: list[UUID], tag_ids: list[int]) -> int:
        validated_asset_ids = self.validate_asset_ids(asset_ids)
        validated_tag_ids = self.validate_tag_ids(tag_ids)
        return self.repository.batch_remove_tags(
            asset_ids=validated_asset_ids,
            tag_ids=validated_tag_ids,
        )

    def _validate_cover_asset(self, *, tag: Tag, cover_asset_id: UUID) -> UUID:
        self.validate_asset_ids([cover_asset_id])
        if not self.repository.asset_belongs_to_tag_subtree(
            asset_id=cover_asset_id,
            tag_path=tag.path,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cover asset must belong to tag directly or through descendant",
            )
        return cover_asset_id


def get_tag_service(session: Session = Depends(get_session)) -> TagService:
    return TagService(session)
