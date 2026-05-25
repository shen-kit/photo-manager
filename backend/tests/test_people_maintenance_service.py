from __future__ import annotations

import unittest
from uuid import uuid4

from app.models import Person
from app.services.people.maintenance import PeopleMaintenanceService


class _FakePeopleRepository:
    def __init__(self, people: list[Person], orphaned_ids: list) -> None:
        self.people = {person.id: person for person in people}
        self.orphaned_ids = list(orphaned_ids)
        self.deleted_people: list[Person] = []

    def list_people_by_ids(self, person_ids):
        return [
            self.people[person_id]
            for person_id in person_ids
            if person_id in self.people
        ]

    def list_person_ids_without_active_assets(self, *, person_ids):
        requested = set(person_ids)
        return [person_id for person_id in self.orphaned_ids if person_id in requested]

    def delete_people(self, people):
        self.deleted_people.extend(people)
        for person in people:
            self.people.pop(person.id, None)
        return [person.id for person in people]

    def list_existing_person_ids(self, person_ids):
        return [person_id for person_id in person_ids if person_id in self.people]


class _FakeThumbnailService:
    def __init__(self) -> None:
        self.deleted_paths: list[str | None] = []
        self.ensure_calls: list[str] = []

    def delete_thumbnail_file(self, thumbnail_path):
        self.deleted_paths.append(thumbnail_path)

    def ensure_thumbnail(self, *, person_id):
        self.ensure_calls.append(str(person_id))


class PeopleMaintenanceServiceTest(unittest.TestCase):
    def _person(self, *, thumbnail_path: str | None = None) -> Person:
        return Person(
            id=uuid4(),
            name=None,
            thumbnail_face_id=None,
            thumbnail_path=thumbnail_path,
            thumbnail_manually_set=False,
            is_hidden=False,
        )

    def test_deletes_people_without_active_assets_and_refreshes_remaining(self) -> None:
        kept_person = self._person(
            thumbnail_path="generated/people/thumbnails/keep.webp"
        )
        orphaned_person = self._person(
            thumbnail_path="generated/people/thumbnails/delete.webp"
        )
        repository = _FakePeopleRepository(
            [kept_person, orphaned_person],
            orphaned_ids=[orphaned_person.id],
        )
        thumbnail_service = _FakeThumbnailService()
        service = PeopleMaintenanceService(
            session=None,
            repository=repository,
            thumbnail_service=thumbnail_service,
        )

        result = service.reconcile_people(
            person_ids=[kept_person.id, orphaned_person.id]
        )

        self.assertEqual(result.deleted_person_ids, [orphaned_person.id])
        self.assertEqual(result.retained_person_ids, [kept_person.id])
        self.assertEqual(
            [person.id for person in repository.deleted_people],
            [orphaned_person.id],
        )
        self.assertEqual(
            thumbnail_service.deleted_paths,
            ["generated/people/thumbnails/delete.webp"],
        )
        self.assertEqual(thumbnail_service.ensure_calls, [str(kept_person.id)])

    def test_skips_thumbnail_refresh_when_requested(self) -> None:
        person = self._person()
        repository = _FakePeopleRepository([person], orphaned_ids=[])
        thumbnail_service = _FakeThumbnailService()
        service = PeopleMaintenanceService(
            session=None,
            repository=repository,
            thumbnail_service=thumbnail_service,
        )

        result = service.reconcile_people(
            person_ids=[person.id],
            refresh_thumbnails=False,
        )

        self.assertEqual(result.deleted_person_ids, [])
        self.assertEqual(result.retained_person_ids, [person.id])
        self.assertEqual(thumbnail_service.ensure_calls, [])


if __name__ == "__main__":
    unittest.main()
