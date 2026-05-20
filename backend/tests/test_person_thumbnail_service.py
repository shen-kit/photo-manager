from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.models import Person
from app.services.people.repository import PersonThumbnailCandidate
from app.services.people.thumbnails import (
    PersonThumbnailService,
    PersonThumbnailServiceError,
)


class _FakePeopleRepository:
    def __init__(
        self,
        person: Person,
        *,
        manual_candidate: PersonThumbnailCandidate | None = None,
        auto_candidates: list[PersonThumbnailCandidate] | None = None,
    ) -> None:
        self.person = person
        self.manual_candidate = manual_candidate
        self.auto_candidates = auto_candidates or []
        self.updated_people: list[Person] = []

    def get_person(self, person_id):
        if self.person.id == person_id:
            return self.person
        return None

    def get_thumbnail_candidate(self, *, person_id, face_id):
        if (
            self.manual_candidate is not None
            and person_id == self.person.id
            and face_id == self.manual_candidate.face_id
        ):
            return self.manual_candidate
        return None

    def get_thumbnail_candidate_for_asset(self, *, person_id, asset_id):
        if (
            self.manual_candidate is not None
            and person_id == self.person.id
            and asset_id == self.manual_candidate.asset_id
        ):
            return self.manual_candidate
        return None

    def list_thumbnail_candidates_for_person(self, *, person_id):
        if person_id != self.person.id:
            return []
        return list(self.auto_candidates)

    def update_person(self, person: Person):
        self.updated_people.append(person)
        self.person = person
        return person


class PersonThumbnailServiceTest(unittest.TestCase):
    def _person(self) -> Person:
        return Person(
            id=uuid4(),
            name=None,
            thumbnail_face_id=None,
            thumbnail_path=None,
            thumbnail_manually_set=False,
            is_hidden=False,
        )

    def _candidate(
        self,
        *,
        face_id=None,
        confidence: float | None,
        width: int,
        height: int,
        master_path: str = "2026/05/example.jpg",
    ) -> PersonThumbnailCandidate:
        return PersonThumbnailCandidate(
            face_id=face_id or uuid4(),
            asset_id=uuid4(),
            master_path=master_path,
            mime_type="image/jpeg",
            bounding_box={
                "x": 20,
                "y": 10,
                "width": width,
                "height": height,
                "image_width": 200,
                "image_height": 100,
            },
            confidence=confidence,
        )

    def test_best_face_selection_uses_confidence_times_area(self) -> None:
        person = self._person()
        small_high_conf = self._candidate(confidence=0.9, width=10, height=10)
        large_lower_conf = self._candidate(confidence=0.4, width=40, height=40)
        repository = _FakePeopleRepository(
            person,
            auto_candidates=[small_high_conf, large_lower_conf],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PersonThumbnailService(
                session=None,
                repository=repository,
                processed_dir=Path(temp_dir),
                image_loader=lambda _: Image.new("RGB", (200, 100), color=(10, 20, 30)),
            )

            result = service.ensure_thumbnail(person_id=person.id)

        self.assertEqual(result.thumbnail_face_id, large_lower_conf.face_id)
        self.assertFalse(result.thumbnail_manually_set)

    def test_manual_thumbnail_requires_valid_face(self) -> None:
        person = self._person()
        repository = _FakePeopleRepository(person)
        service = PersonThumbnailService(
            session=None,
            repository=repository,
            image_loader=lambda _: Image.new("RGB", (100, 100), color=(1, 2, 3)),
        )

        with self.assertRaises(PersonThumbnailServiceError):
            service.set_manual_thumbnail(person_id=person.id, asset_id=uuid4())

    def test_stable_thumbnail_path_is_overwritten(self) -> None:
        person = self._person()
        first_face = self._candidate(
            confidence=0.6, width=20, height=20, master_path="first.jpg"
        )
        second_face = self._candidate(
            confidence=0.7,
            width=30,
            height=30,
            master_path="second.jpg",
        )
        repository = _FakePeopleRepository(person, manual_candidate=first_face)
        colors = {
            "first.jpg": (255, 0, 0),
            "second.jpg": (0, 255, 0),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PersonThumbnailService(
                session=None,
                repository=repository,
                processed_dir=Path(temp_dir),
                image_loader=lambda path: Image.new(
                    "RGB", (120, 120), color=colors[path.name]
                ),
            )

            first_result = service.set_manual_thumbnail(
                person_id=person.id,
                asset_id=first_face.asset_id,
            )
            first_output = Path(temp_dir) / first_result.thumbnail_path
            first_pixel = Image.open(first_output).convert("RGB").getpixel((10, 10))

            repository.manual_candidate = second_face
            second_result = service.set_manual_thumbnail(
                person_id=person.id,
                asset_id=second_face.asset_id,
            )
            second_output = Path(temp_dir) / second_result.thumbnail_path
            second_pixel = Image.open(second_output).convert("RGB").getpixel((10, 10))

        self.assertEqual(first_result.thumbnail_path, second_result.thumbnail_path)
        self.assertEqual(first_output, second_output)
        self.assertNotEqual(first_pixel, second_pixel)

    def test_manual_thumbnail_is_not_overwritten_by_auto_flow(self) -> None:
        person = self._person()
        manual_face = self._candidate(confidence=0.4, width=20, height=20)
        better_auto_face = self._candidate(confidence=0.9, width=50, height=50)
        person.thumbnail_face_id = manual_face.face_id
        person.thumbnail_path = f"generated/people/thumbnails/{person.id}.webp"
        person.thumbnail_manually_set = True
        repository = _FakePeopleRepository(
            person,
            manual_candidate=manual_face,
            auto_candidates=[better_auto_face],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PersonThumbnailService(
                session=None,
                repository=repository,
                processed_dir=Path(temp_dir),
                image_loader=lambda _: Image.new("RGB", (160, 160), color=(9, 9, 9)),
            )

            result = service.ensure_thumbnail(person_id=person.id)

        self.assertEqual(result.thumbnail_face_id, manual_face.face_id)
        self.assertTrue(result.thumbnail_manually_set)


if __name__ == "__main__":
    unittest.main()
