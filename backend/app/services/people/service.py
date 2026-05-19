from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.models import Asset, Person
from app.services.people.repository import PeopleRepository, PersonReadRow


class PeopleServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersonDetail:
    person: Person
    face_count: int
    asset_count: int
    thumbnail_crop_path: str | None


@dataclass(frozen=True)
class PersonMergeSummary:
    faces_moved: int
    source_deleted: bool
    target_person_id: UUID


class PeopleService:
    def __init__(self, session: Session, *, repository: PeopleRepository | None = None) -> None:
        self.session = session
        self.repository = repository or PeopleRepository(session)

    def list_people(
        self,
        *,
        include_hidden: bool = False,
        search: str | None = None,
    ) -> list[PersonReadRow]:
        normalized_search = search.strip() if search else None
        return self.repository.list_people(
            include_hidden=include_hidden,
            search=normalized_search or None,
        )

    def get_person_detail(self, person_id: UUID) -> PersonDetail:
        row = self.repository.get_person_read_row(person_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Person not found",
            )
        return PersonDetail(
            person=row.person,
            face_count=row.face_count,
            asset_count=row.asset_count,
            thumbnail_crop_path=row.thumbnail_crop_path,
        )

    def update_person(
        self,
        person_id: UUID,
        *,
        name: str | None | object = ...,
        is_hidden: bool | object = ...,
        thumbnail_face_id: UUID | None | object = ...,
    ) -> PersonDetail:
        person = self.repository.get_person(person_id)
        if person is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Person not found",
            )
        if thumbnail_face_id is not ... and thumbnail_face_id is not None:
            if not self.repository.face_belongs_to_person(
                face_id=thumbnail_face_id,
                person_id=person_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="thumbnail_face_id must belong to the person",
                )
        if name is not ...:
            person.name = name
        if is_hidden is not ...:
            person.is_hidden = is_hidden
        if thumbnail_face_id is not ...:
            person.thumbnail_face_id = thumbnail_face_id
        self.repository.update_person(person)
        return self.get_person_detail(person_id)

    def list_assets_for_person(
        self,
        *,
        person_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[int, list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]]:
        self.get_person_detail(person_id)
        offset = (page - 1) * page_size
        total = self.repository.count_assets_for_person(person_id=person_id)
        rows = self.repository.list_assets_for_person(
            person_id=person_id,
            limit=page_size,
            offset=offset,
        )
        return total, rows

    def validate_person_ids(self, person_ids: list[UUID]) -> list[UUID]:
        unique_person_ids: list[UUID] = []
        seen: set[UUID] = set()
        for person_id in person_ids:
            if person_id in seen:
                continue
            seen.add(person_id)
            unique_person_ids.append(person_id)
        existing_ids = set(self.repository.list_existing_person_ids(unique_person_ids))
        missing_ids = [person_id for person_id in unique_person_ids if person_id not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more people were not found",
            )
        return unique_person_ids

    def merge_people(
        self,
        *,
        source_person_id: UUID,
        target_person_id: UUID,
    ) -> PersonMergeSummary:
        if source_person_id == target_person_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_person_id and target_person_id must differ",
            )
        source_person = self.repository.get_person(source_person_id)
        target_person = self.repository.get_person(target_person_id)
        if source_person is None or target_person is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Person not found",
            )
        faces_moved, source_deleted = self.repository.merge_people(
            source_person=source_person,
            target_person=target_person,
        )
        return PersonMergeSummary(
            faces_moved=faces_moved,
            source_deleted=source_deleted,
            target_person_id=target_person_id,
        )


def get_people_service(session: Session = Depends(get_session)) -> PeopleService:
    return PeopleService(session)
