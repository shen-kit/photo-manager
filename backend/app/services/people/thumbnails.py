from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from PIL.Image import Image as PILImage
from sqlmodel import Session

from app.models import Person
from app.services.assets.media import (
    MEDIA_PROCESSED_DIR,
    load_oriented_rgb_image,
    master_path_to_source_path,
)
from app.services.people.repository import PeopleRepository, PersonThumbnailCandidate

PERSON_THUMBNAIL_SIZE = 256
PERSON_THUMBNAIL_QUALITY = 85
PERSON_THUMBNAIL_RELATIVE_DIR = Path("generated/people/thumbnails")


class PersonThumbnailServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersonThumbnailResult:
    person_id: UUID
    thumbnail_face_id: UUID | None
    thumbnail_path: str | None
    thumbnail_manually_set: bool


class PersonThumbnailService:
    def __init__(
        self,
        session: Session,
        *,
        repository: PeopleRepository | None = None,
        image_loader: Callable[[Path], PILImage] = load_oriented_rgb_image,
        processed_dir: Path = MEDIA_PROCESSED_DIR,
    ) -> None:
        self.session = session
        self.repository = repository or PeopleRepository(session)
        self.image_loader = image_loader
        self.processed_dir = processed_dir

    def set_manual_thumbnail(
        self,
        *,
        person_id: UUID,
        asset_id: UUID,
    ) -> PersonThumbnailResult:
        person = self._require_person(person_id)
        candidate = self.repository.get_thumbnail_candidate_for_asset(
            person_id=person_id,
            asset_id=asset_id,
        )
        if candidate is None:
            raise PersonThumbnailServiceError(
                "asset_id must contain a non-excluded face for the person"
            )
        return self._render_and_persist(
            person=person,
            candidate=candidate,
            thumbnail_manually_set=True,
        )

    def ensure_thumbnail(self, *, person_id: UUID) -> PersonThumbnailResult:
        person = self._require_person(person_id)
        current_candidate = None
        if person.thumbnail_face_id is not None:
            current_candidate = self.repository.get_thumbnail_candidate(
                person_id=person_id,
                face_id=person.thumbnail_face_id,
            )

        if person.thumbnail_manually_set:
            if current_candidate is not None:
                return self._render_and_persist(
                    person=person,
                    candidate=current_candidate,
                    thumbnail_manually_set=True,
                )
            return self._clear_thumbnail(person=person, thumbnail_manually_set=False)

        candidates = self.repository.list_thumbnail_candidates_for_person(
            person_id=person_id
        )
        candidate = self._select_best_candidate(candidates)
        if candidate is None:
            return self._clear_thumbnail(person=person, thumbnail_manually_set=False)
        return self._render_and_persist(
            person=person,
            candidate=candidate,
            thumbnail_manually_set=False,
        )

    def delete_thumbnail_file(self, thumbnail_path: str | None) -> None:
        if not thumbnail_path:
            return
        output_path = (self.processed_dir / thumbnail_path).resolve()
        output_path.unlink(missing_ok=True)

    def _render_and_persist(
        self,
        *,
        person: Person,
        candidate: PersonThumbnailCandidate,
        thumbnail_manually_set: bool,
    ) -> PersonThumbnailResult:
        source_path = master_path_to_source_path(candidate.master_path)
        image = self.image_loader(source_path)
        rendered = self._render_thumbnail(image=image, candidate=candidate)
        thumbnail_path = self._thumbnail_relative_path(person.id)
        output_path = self.processed_dir / thumbnail_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rendered.save(output_path, format="WEBP", quality=PERSON_THUMBNAIL_QUALITY)

        person.thumbnail_face_id = candidate.face_id
        person.thumbnail_path = thumbnail_path.as_posix()
        person.thumbnail_manually_set = thumbnail_manually_set
        self.repository.update_person(person)
        return PersonThumbnailResult(
            person_id=person.id,
            thumbnail_face_id=person.thumbnail_face_id,
            thumbnail_path=person.thumbnail_path,
            thumbnail_manually_set=person.thumbnail_manually_set,
        )

    def _clear_thumbnail(
        self,
        *,
        person: Person,
        thumbnail_manually_set: bool,
    ) -> PersonThumbnailResult:
        self.delete_thumbnail_file(person.thumbnail_path)
        person.thumbnail_face_id = None
        person.thumbnail_path = None
        person.thumbnail_manually_set = thumbnail_manually_set
        self.repository.update_person(person)
        return PersonThumbnailResult(
            person_id=person.id,
            thumbnail_face_id=None,
            thumbnail_path=None,
            thumbnail_manually_set=person.thumbnail_manually_set,
        )

    def _require_person(self, person_id: UUID) -> Person:
        person = self.repository.get_person(person_id)
        if person is None:
            raise PersonThumbnailServiceError(f"Person {person_id} not found")
        return person

    @staticmethod
    def _select_best_candidate(
        candidates: list[PersonThumbnailCandidate],
    ) -> PersonThumbnailCandidate | None:
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (
                PersonThumbnailService._candidate_score(candidate),
                candidate.confidence or 0.0,
                str(candidate.face_id),
            ),
        )

    @staticmethod
    def _candidate_score(candidate: PersonThumbnailCandidate) -> float:
        box = candidate.bounding_box
        width = max(int(box.get("width", 0)), 0)
        height = max(int(box.get("height", 0)), 0)
        return (candidate.confidence or 0.0) * float(width * height)

    @staticmethod
    def _thumbnail_relative_path(person_id: UUID) -> Path:
        return PERSON_THUMBNAIL_RELATIVE_DIR / f"{person_id}.webp"

    @staticmethod
    def _render_thumbnail(
        *,
        image: PILImage,
        candidate: PersonThumbnailCandidate,
    ) -> PILImage:
        box = candidate.bounding_box
        image_width, image_height = image.size
        x = max(int(box.get("x", 0)), 0)
        y = max(int(box.get("y", 0)), 0)
        width = max(int(box.get("width", 0)), 1)
        height = max(int(box.get("height", 0)), 1)

        center_x = x + (width / 2)
        center_y = y + (height / 2)
        padded_width = width * 2.0
        padded_height = height * 2.0
        side = max(padded_width, padded_height, 1.0)

        left = center_x - (side / 2)
        top = center_y - (side / 2)
        right = center_x + (side / 2)
        bottom = center_y + (side / 2)

        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > image_width:
            left -= right - image_width
            right = image_width
        if bottom > image_height:
            top -= bottom - image_height
            bottom = image_height

        left = max(int(round(left)), 0)
        top = max(int(round(top)), 0)
        right = min(int(round(right)), image_width)
        bottom = min(int(round(bottom)), image_height)

        if right <= left:
            right = min(left + 1, image_width)
        if bottom <= top:
            bottom = min(top + 1, image_height)

        cropped = image.crop((left, top, right, bottom))
        return cropped.resize((PERSON_THUMBNAIL_SIZE, PERSON_THUMBNAIL_SIZE))
