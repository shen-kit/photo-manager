from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Face, Person
from app.services.faces.service import FaceManagementService, FaceManagementServiceError


class _FakeFaceRepository:
    def __init__(self, face: Face | None, person: Person | None = None) -> None:
        self.face = face
        self.person = person
        self.updated_face: Face | None = None

    def get_face(self, face_id):
        if self.face and self.face.id == face_id:
            return self.face
        return None

    def get_person(self, person_id):
        if self.person and self.person.id == person_id:
            return self.person
        return None

    def update_face(self, face: Face) -> Face:
        self.updated_face = face
        self.face = face
        return face


class _FakeThumbnailService:
    def __init__(self) -> None:
        self.ensure_calls: list[str] = []

    def ensure_thumbnail(self, *, person_id):
        self.ensure_calls.append(str(person_id))


class FaceManagementServiceTest(unittest.TestCase):
    def _face(self) -> Face:
        return Face(
            id=uuid4(),
            asset_id=uuid4(),
            person_id=None,
            bounding_box={},
            embedding=None,
            confidence=0.9,
            crop_path=None,
            is_confirmed=False,
            is_excluded=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def _person(self) -> Person:
        return Person(id=uuid4(), name=None, thumbnail_face_id=None, is_hidden=False)

    def test_assigning_face_to_person_sets_confirmed(self) -> None:
        face = self._face()
        person = self._person()
        repository = _FakeFaceRepository(face, person)
        thumbnail_service = _FakeThumbnailService()
        service = FaceManagementService(
            session=None,
            repository=repository,
            thumbnail_service=thumbnail_service,
        )

        updated = service.update_face(face.id, person_id=person.id)

        self.assertEqual(updated.person_id, person.id)
        self.assertTrue(updated.is_confirmed)
        self.assertFalse(updated.is_excluded)
        self.assertEqual(thumbnail_service.ensure_calls, [str(person.id)])

    def test_assigning_face_to_missing_person_fails(self) -> None:
        face = self._face()
        repository = _FakeFaceRepository(face, None)
        service = FaceManagementService(
            session=None,
            repository=repository,
            thumbnail_service=_FakeThumbnailService(),
        )

        with self.assertRaises(FaceManagementServiceError) as exc:
            service.update_face(face.id, person_id=uuid4())

        self.assertIn("not found", str(exc.exception).lower())

    def test_excluded_face_requires_explicit_unexclude_before_assignment(self) -> None:
        face = self._face()
        face.is_excluded = True
        person = self._person()
        repository = _FakeFaceRepository(face, person)
        service = FaceManagementService(
            session=None,
            repository=repository,
            thumbnail_service=_FakeThumbnailService(),
        )

        with self.assertRaises(FaceManagementServiceError) as exc:
            service.update_face(face.id, person_id=person.id)

        self.assertIn("explicitly unexcluding", str(exc.exception).lower())

    def test_assigning_excluded_face_with_explicit_unexclude_succeeds(self) -> None:
        face = self._face()
        face.is_excluded = True
        person = self._person()
        repository = _FakeFaceRepository(face, person)
        thumbnail_service = _FakeThumbnailService()
        service = FaceManagementService(
            session=None,
            repository=repository,
            thumbnail_service=thumbnail_service,
        )

        updated = service.update_face(
            face.id,
            person_id=person.id,
            is_excluded=False,
        )

        self.assertEqual(updated.person_id, person.id)
        self.assertFalse(updated.is_excluded)
        self.assertTrue(updated.is_confirmed)
        self.assertEqual(thumbnail_service.ensure_calls, [str(person.id)])


if __name__ == "__main__":
    unittest.main()
