from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models import Tag
from app.services.tags.service import TagService, slugify_tag_name


class _FakeRepository:
    def __init__(self, tags: list[Tag] | None = None) -> None:
        self.tags = {tag.id: tag for tag in tags or [] if tag.id is not None}
        self.asset_membership: dict[tuple[str, object], bool] = {}
        self.add_calls: list[tuple[object, int]] = []
        self.remove_calls: list[tuple[object, int]] = []
        self.batch_add_calls: list[tuple[list[object], list[int]]] = []
        self.batch_remove_calls: list[tuple[list[object], list[int]]] = []

    def get_tag(self, tag_id: int):
        return self.tags.get(tag_id)

    def list_tags(self, **kwargs):
        del kwargs
        return list(self.tags.values())

    def list_existing_tag_ids(self, tag_ids: list[int]) -> list[int]:
        return [tag_id for tag_id in tag_ids if tag_id in self.tags]

    def list_existing_asset_ids(self, asset_ids: list[object]) -> list[object]:
        return list(asset_ids)

    def create_tag(self, tag: Tag) -> Tag:
        tag.id = max(self.tags.keys(), default=0) + 1
        self.tags[tag.id] = tag
        return tag

    def save_tag(self, tag: Tag) -> Tag:
        self.tags[tag.id] = tag
        return tag

    def path_exists(self, path: str, *, exclude_tag_id: int | None = None) -> bool:
        for tag in self.tags.values():
            if tag.path == path and tag.id != exclude_tag_id:
                return True
        return False

    def count_descendants(self, tag_path: str) -> int:
        return sum(
            1 for tag in self.tags.values() if tag.path.startswith(tag_path + ".")
        )

    def update_descendant_paths(self, *, old_path: str, new_path: str) -> None:
        for tag in self.tags.values():
            if tag.path.startswith(old_path + "."):
                tag.path = new_path + tag.path[len(old_path) :]

    def delete_tag_subtree(self, *, tag_path: str) -> None:
        to_delete = [
            tag_id
            for tag_id, tag in self.tags.items()
            if tag.path == tag_path or tag.path.startswith(tag_path + ".")
        ]
        for tag_id in to_delete:
            self.tags.pop(tag_id, None)

    def asset_belongs_to_tag_subtree(self, *, asset_id, tag_path: str) -> bool:
        return self.asset_membership.get((tag_path, asset_id), False)

    def add_tag_to_asset(self, *, asset_id, tag_id: int) -> None:
        self.add_calls.append((asset_id, tag_id))

    def remove_tag_from_asset(self, *, asset_id, tag_id: int) -> None:
        self.remove_calls.append((asset_id, tag_id))

    def batch_add_tags(self, *, asset_ids, tag_ids) -> int:
        self.batch_add_calls.append((list(asset_ids), list(tag_ids)))
        return len(asset_ids) * len(tag_ids)

    def batch_remove_tags(self, *, asset_ids, tag_ids) -> int:
        self.batch_remove_calls.append((list(asset_ids), list(tag_ids)))
        return len(asset_ids) * len(tag_ids)

    def build_delete_conflict_detail(self, *, tag: Tag, descendant_count: int):
        return {
            "code": "tag_has_children",
            "tag_id": tag.id,
            "descendant_count": descendant_count,
        }


def _tag(
    *, tag_id: int, name: str, slug: str, path: str, is_album: bool = False
) -> Tag:
    now = datetime.now(timezone.utc)
    return Tag(
        id=tag_id,
        name=name,
        slug=slug,
        path=path,
        is_album=is_album,
        created_at=now,
        updated_at=now,
    )


class TagServiceTest(unittest.TestCase):
    def test_slugify_normalizes_user_name(self) -> None:
        self.assertEqual(slugify_tag_name("China 2026"), "china_2026")
        self.assertEqual(slugify_tag_name("China-2026"), "china_2026")

    def test_delete_branch_requires_confirmation(self) -> None:
        repository = _FakeRepository(
            [
                _tag(tag_id=1, name="Holidays", slug="holidays", path="holidays"),
                _tag(
                    tag_id=2,
                    name="China 2026",
                    slug="china_2026",
                    path="holidays.china_2026",
                ),
            ]
        )
        service = TagService(session=None, repository=repository)

        with self.assertRaises(HTTPException) as context:
            service.delete_tag(1, delete_children=False)

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail["code"], "tag_has_children")

    def test_delete_branch_with_confirmation_removes_subtree(self) -> None:
        repository = _FakeRepository(
            [
                _tag(tag_id=1, name="Holidays", slug="holidays", path="holidays"),
                _tag(
                    tag_id=2,
                    name="China 2026",
                    slug="china_2026",
                    path="holidays.china_2026",
                ),
            ]
        )
        service = TagService(session=None, repository=repository)

        service.delete_tag(1, delete_children=True)

        self.assertEqual(repository.tags, {})

    def test_cover_asset_requires_descendant_membership(self) -> None:
        root = _tag(tag_id=1, name="Holidays", slug="holidays", path="holidays")
        repository = _FakeRepository([root])
        asset_id = uuid4()
        repository.asset_membership[(root.path, asset_id)] = True
        service = TagService(session=None, repository=repository)

        updated = service.update_tag(
            1,
            cover_asset_id=asset_id,
        )

        self.assertEqual(updated.cover_asset_id, asset_id)

    def test_batch_add_validates_and_calls_repository(self) -> None:
        repository = _FakeRepository(
            [_tag(tag_id=4, name="Holidays", slug="holidays", path="holidays")]
        )
        service = TagService(session=None, repository=repository)
        asset_ids = [uuid4(), uuid4()]

        updated_count = service.batch_add_tags(asset_ids=asset_ids, tag_ids=[4])

        self.assertEqual(updated_count, 2)
        self.assertEqual(repository.batch_add_calls, [(asset_ids, [4])])


if __name__ == "__main__":
    unittest.main()
