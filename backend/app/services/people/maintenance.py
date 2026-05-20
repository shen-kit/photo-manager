from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.services.people.repository import PeopleRepository
from app.services.people.thumbnails import PersonThumbnailService


@dataclass(frozen=True)
class PeopleMaintenanceResult:
    deleted_person_ids: list[UUID]
    retained_person_ids: list[UUID]


class PeopleMaintenanceService:
    def __init__(
        self,
        session: Session,
        *,
        repository: PeopleRepository | None = None,
        thumbnail_service: PersonThumbnailService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or PeopleRepository(session)
        self.thumbnail_service = thumbnail_service or PersonThumbnailService(
            session,
            repository=self.repository,
        )

    def reconcile_people(
        self,
        *,
        person_ids: list[UUID],
        refresh_thumbnails: bool = True,
    ) -> PeopleMaintenanceResult:
        unique_person_ids: list[UUID] = []
        seen: set[UUID] = set()
        for person_id in person_ids:
            if person_id in seen:
                continue
            seen.add(person_id)
            unique_person_ids.append(person_id)
        if not unique_person_ids:
            return PeopleMaintenanceResult(
                deleted_person_ids=[], retained_person_ids=[]
            )

        people = self.repository.list_people_by_ids(unique_person_ids)
        if not people:
            return PeopleMaintenanceResult(
                deleted_person_ids=[], retained_person_ids=[]
            )

        orphaned_ids = set(
            self.repository.list_person_ids_without_active_assets(
                person_ids=[person.id for person in people]
            )
        )
        orphaned_people = [person for person in people if person.id in orphaned_ids]
        retained_person_ids = [
            person.id for person in people if person.id not in orphaned_ids
        ]

        deleted_thumbnail_paths = [person.thumbnail_path for person in orphaned_people]
        deleted_person_ids = self.repository.delete_people(orphaned_people)
        for thumbnail_path in deleted_thumbnail_paths:
            self.thumbnail_service.delete_thumbnail_file(thumbnail_path)

        if refresh_thumbnails:
            for person_id in retained_person_ids:
                self.thumbnail_service.ensure_thumbnail(person_id=person_id)

        return PeopleMaintenanceResult(
            deleted_person_ids=deleted_person_ids,
            retained_person_ids=retained_person_ids,
        )
