from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models import Person
from app.services.people.repository import PersonReadRow
from app.services.people.service import PeopleService


class _FakePeopleRepository:
    def __init__(self, person: Person | None) -> None:
        self.person = person
        self.updated_person: Person | None = None
        self.face_belongs = True
        self.person_rows: dict[str, PersonReadRow] = {}
        self.existing_person_ids: list = []

    def list_people(self, *, include_hidden: bool, search: str | None):
        return []

    def get_person(self, person_id):
        if self.person and self.person.id == person_id:
            return self.person
        return None

    def get_person_read_row(self, person_id):
        return self.person_rows.get(str(person_id))

    def face_belongs_to_person(self, *, face_id, person_id):
        return self.face_belongs

    def update_person(self, person: Person):
        self.updated_person = person
        self.person = person
        return person

    def list_existing_person_ids(self, person_ids):
        return list(self.existing_person_ids)

    def count_assets_for_person(self, *, person_id):
        return 0

    def list_assets_for_person(self, *, person_id, limit, offset):
        return []


class PeopleServiceTest(unittest.TestCase):
    def _person(self) -> Person:
        return Person(id=uuid4(), name=None, thumbnail_face_id=None, is_hidden=False)

    def _row(self, person: Person) -> PersonReadRow:
        return PersonReadRow(
            person=person,
            face_count=3,
            asset_count=2,
            thumbnail_crop_path=None,
        )

    def test_update_person_renames_and_hides(self) -> None:
        person = self._person()
        repo = _FakePeopleRepository(person)
        repo.person_rows[str(person.id)] = self._row(person)
        service = PeopleService(session=None, repository=repo)

        updated = service.update_person(
            person.id,
            name="Alice",
            is_hidden=True,
        )

        self.assertEqual(repo.updated_person.name, "Alice")
        self.assertTrue(repo.updated_person.is_hidden)
        self.assertEqual(updated.person.name, "Alice")
        self.assertTrue(updated.person.is_hidden)

    def test_update_person_validates_thumbnail_face_belongs(self) -> None:
        person = self._person()
        repo = _FakePeopleRepository(person)
        repo.face_belongs = False
        service = PeopleService(session=None, repository=repo)

        with self.assertRaises(HTTPException) as exc:
            service.update_person(person.id, thumbnail_face_id=uuid4())

        self.assertEqual(exc.exception.status_code, 400)

    def test_validate_person_ids_rejects_missing_people(self) -> None:
        person_a = uuid4()
        person_b = uuid4()
        repo = _FakePeopleRepository(None)
        repo.existing_person_ids = [person_a]
        service = PeopleService(session=None, repository=repo)

        with self.assertRaises(HTTPException) as exc:
            service.validate_person_ids([person_a, person_b])

        self.assertEqual(exc.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
