from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import case, func
from sqlmodel import Session, select

from app.models import Asset, AssetTag, Face, Person, Tag


@dataclass(frozen=True)
class PersonReadRow:
    person: Person
    face_count: int
    asset_count: int
    thumbnail_path: str | None


@dataclass(frozen=True)
class PersonThumbnailCandidate:
    face_id: UUID
    asset_id: UUID
    master_path: str
    mime_type: str
    bounding_box: dict[str, Any]
    confidence: float | None


class PeopleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_people(
        self,
        *,
        include_hidden: bool,
        search: str | None,
    ) -> list[PersonReadRow]:
        stats_subquery = self._person_stats_subquery()
        named_sort = self._named_person_sort_expression()
        statement = (
            select(
                Person,
                func.coalesce(stats_subquery.c.face_count, 0),
                func.coalesce(stats_subquery.c.asset_count, 0),
                Face.crop_path,
            )
            .outerjoin(stats_subquery, stats_subquery.c.person_id == Person.id)
            .outerjoin(Face, Face.id == Person.thumbnail_face_id)
        )
        statement = statement.where(func.coalesce(stats_subquery.c.asset_count, 0) > 0)
        if not include_hidden:
            statement = statement.where(Person.is_hidden.is_(False))
        if search:
            statement = statement.where(Person.name.ilike(f"%{search}%"))
        statement = statement.order_by(
            named_sort.asc(),
            func.coalesce(stats_subquery.c.asset_count, 0).desc(),
            func.coalesce(stats_subquery.c.face_count, 0).desc(),
            Person.name.asc().nullslast(),
            Person.id.asc(),
        )
        return [
            PersonReadRow(
                person=person,
                face_count=int(face_count),
                asset_count=int(asset_count),
                thumbnail_path=person.thumbnail_path,
            )
            for person, face_count, asset_count, crop_path in self.session.exec(
                statement
            ).all()
        ]

    def get_person(self, person_id: UUID) -> Person | None:
        return self.session.get(Person, person_id)

    def get_person_read_row(self, person_id: UUID) -> PersonReadRow | None:
        stats_subquery = self._person_stats_subquery()
        statement = (
            select(
                Person,
                func.coalesce(stats_subquery.c.face_count, 0),
                func.coalesce(stats_subquery.c.asset_count, 0),
                Face.crop_path,
            )
            .outerjoin(stats_subquery, stats_subquery.c.person_id == Person.id)
            .outerjoin(Face, Face.id == Person.thumbnail_face_id)
            .where(
                Person.id == person_id,
                func.coalesce(stats_subquery.c.asset_count, 0) > 0,
            )
        )
        row = self.session.exec(statement).first()
        if row is None:
            return None
        person, face_count, asset_count, crop_path = row
        return PersonReadRow(
            person=person,
            face_count=int(face_count),
            asset_count=int(asset_count),
            thumbnail_path=person.thumbnail_path,
        )

    def face_belongs_to_person(self, *, face_id: UUID, person_id: UUID) -> bool:
        statement = select(Face.id).where(
            Face.id == face_id, Face.person_id == person_id
        )
        return self.session.exec(statement).first() is not None

    def update_person(self, person: Person) -> Person:
        self.session.add(person)
        self.session.commit()
        self.session.refresh(person)
        return person

    def get_thumbnail_candidate(
        self,
        *,
        person_id: UUID,
        face_id: UUID,
    ) -> PersonThumbnailCandidate | None:
        statement = (
            select(
                Face.id,
                Face.asset_id,
                Asset.master_path,
                Asset.mime_type,
                Face.bounding_box,
                Face.confidence,
            )
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Face.id == face_id,
                Face.person_id == person_id,
                Face.is_excluded.is_(False),
                Face.asset_id.is_not(None),
                Asset.deleted_at.is_(None),
            )
        )
        row = self.session.exec(statement).first()
        return self._thumbnail_candidate_from_row(row)

    def get_thumbnail_candidate_for_asset(
        self,
        *,
        person_id: UUID,
        asset_id: UUID,
    ) -> PersonThumbnailCandidate | None:
        statement = (
            select(
                Face.id,
                Face.asset_id,
                Asset.master_path,
                Asset.mime_type,
                Face.bounding_box,
                Face.confidence,
            )
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Face.person_id == person_id,
                Face.asset_id == asset_id,
                Face.is_excluded.is_(False),
                Asset.deleted_at.is_(None),
            )
            .order_by(
                (
                    func.coalesce(Face.confidence, 0.0)
                    * func.greatest(
                        func.coalesce(
                            Face.bounding_box["width"].astext.cast(sa.Integer), 0
                        ),
                        0,
                    )
                    * func.greatest(
                        func.coalesce(
                            Face.bounding_box["height"].astext.cast(sa.Integer), 0
                        ),
                        0,
                    )
                ).desc(),
                func.coalesce(Face.confidence, 0.0).desc(),
                Face.id.asc(),
            )
        )
        row = self.session.exec(statement).first()
        return self._thumbnail_candidate_from_row(row)

    def list_thumbnail_candidates_for_person(
        self,
        *,
        person_id: UUID,
    ) -> list[PersonThumbnailCandidate]:
        statement = (
            select(
                Face.id,
                Face.asset_id,
                Asset.master_path,
                Asset.mime_type,
                Face.bounding_box,
                Face.confidence,
            )
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Face.person_id == person_id,
                Face.is_excluded.is_(False),
                Face.asset_id.is_not(None),
                Asset.deleted_at.is_(None),
            )
            .order_by(Face.created_at.asc(), Face.id.asc())
        )
        rows = self.session.exec(statement).all()
        return [
            candidate
            for candidate in (self._thumbnail_candidate_from_row(row) for row in rows)
            if candidate is not None
        ]

    def merge_people(
        self,
        *,
        source_person: Person,
        target_person: Person,
    ) -> tuple[int, bool]:
        with self.session.begin():
            moved_result = self.session.exec(
                select(Face.id).where(
                    Face.person_id == source_person.id,
                    Face.is_excluded.is_(False),
                )
            )
            moved_face_ids = list(moved_result.all())
            faces_moved = 0
            if moved_face_ids:
                update_result = self.session.exec(
                    Face.__table__.update()
                    .where(Face.id.in_(moved_face_ids))
                    .values(person_id=target_person.id)
                )
                faces_moved = update_result.rowcount or 0

            self.session.exec(
                Face.__table__.update()
                .where(
                    Face.person_id == source_person.id,
                    Face.is_excluded.is_(True),
                )
                .values(person_id=None)
            )

            source_person.thumbnail_face_id = None
            source_person.thumbnail_path = None
            source_person.thumbnail_manually_set = False
            self.session.add(target_person)
            self.session.add(source_person)
            self.session.delete(source_person)

        self.session.refresh(target_person)
        return faces_moved, True

    def list_existing_person_ids(self, person_ids: list[UUID]) -> list[UUID]:
        if not person_ids:
            return []
        stats_subquery = self._person_stats_subquery()
        statement = (
            select(Person.id)
            .outerjoin(stats_subquery, stats_subquery.c.person_id == Person.id)
            .where(
                Person.id.in_(person_ids),
                func.coalesce(stats_subquery.c.asset_count, 0) > 0,
            )
        )
        return list(self.session.exec(statement).all())

    def list_people_by_ids(self, person_ids: list[UUID]) -> list[Person]:
        if not person_ids:
            return []
        statement = select(Person).where(Person.id.in_(person_ids))
        return list(self.session.exec(statement).all())

    def list_person_ids_for_asset(self, *, asset_id: UUID) -> list[UUID]:
        statement = select(func.distinct(Face.person_id)).where(
            Face.asset_id == asset_id, Face.person_id.is_not(None)
        )
        return [
            person_id for person_id in self.session.exec(statement).all() if person_id
        ]

    def list_person_ids_without_active_assets(
        self, *, person_ids: list[UUID]
    ) -> list[UUID]:
        if not person_ids:
            return []
        stats_subquery = self._person_stats_subquery()
        statement = (
            select(Person.id)
            .outerjoin(stats_subquery, stats_subquery.c.person_id == Person.id)
            .where(
                Person.id.in_(person_ids),
                func.coalesce(stats_subquery.c.asset_count, 0) == 0,
            )
        )
        return list(self.session.exec(statement).all())

    def delete_people(self, people: list[Person]) -> list[UUID]:
        if not people:
            return []
        deleted_ids: list[UUID] = []
        for person in people:
            person.thumbnail_face_id = None
            person.thumbnail_path = None
            person.thumbnail_manually_set = False
            self.session.add(person)
            deleted_ids.append(person.id)
            self.session.delete(person)
        self.session.commit()
        return deleted_ids

    def count_assets_for_people(self, *, person_ids: list[UUID]) -> int:
        matching_assets = self._matching_assets_by_people_subquery(person_ids)
        statement = select(func.count()).select_from(matching_assets)
        return int(self.session.exec(statement).one())

    def list_assets_for_people(
        self,
        *,
        person_ids: list[UUID],
        limit: int,
        offset: int,
    ) -> list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]:
        matching_assets = self._matching_assets_by_people_subquery(person_ids)
        return self._hydrate_assets_from_id_subquery(
            matching_assets,
            limit=limit,
            offset=offset,
        )

    def count_assets_for_person(self, *, person_id: UUID) -> int:
        return self.count_assets_for_people(person_ids=[person_id])

    def list_assets_for_person(
        self,
        *,
        person_id: UUID,
        limit: int,
        offset: int,
    ) -> list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]:
        return self.list_assets_for_people(
            person_ids=[person_id],
            limit=limit,
            offset=offset,
        )

    def _person_stats_subquery(self):
        return (
            select(
                Face.person_id.label("person_id"),
                func.count(Face.id).label("face_count"),
                func.count(func.distinct(Face.asset_id)).label("asset_count"),
            )
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Face.person_id.is_not(None),
                Face.is_excluded.is_(False),
                Asset.deleted_at.is_(None),
            )
            .group_by(Face.person_id)
            .subquery()
        )

    @staticmethod
    def _named_person_sort_expression():
        trimmed_name = func.nullif(func.btrim(Person.name), "")
        return case((trimmed_name.is_(None), 1), else_=0)

    def _matching_assets_by_people_subquery(self, person_ids: list[UUID]):
        return (
            select(Face.asset_id.label("asset_id"))
            .join(Asset, Asset.id == Face.asset_id)
            .where(
                Asset.deleted_at.is_(None),
                Face.asset_id.is_not(None),
                Face.is_excluded.is_(False),
                Face.person_id.in_(person_ids),
            )
            .group_by(Face.asset_id)
            .having(func.count(func.distinct(Face.person_id)) == len(person_ids))
            .subquery()
        )

    def _hydrate_assets_from_id_subquery(
        self,
        asset_ids_subquery,
        *,
        limit: int,
        offset: int,
    ) -> list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]]:
        ordered_assets_subquery = (
            select(Asset.id)
            .join(asset_ids_subquery, asset_ids_subquery.c.asset_id == Asset.id)
            .where(Asset.deleted_at.is_(None))
            .order_by(Asset.captured_at.desc().nullslast(), Asset.created_at.desc())
            .offset(offset)
            .limit(limit)
            .subquery()
        )
        asset_ids = list(self.session.exec(select(ordered_assets_subquery.c.id)).all())
        if not asset_ids:
            return []
        ordering = case(
            {asset_id: index for index, asset_id in enumerate(asset_ids)},
            value=Asset.id,
        )
        tags_subquery, faces_subquery = self._asset_relations_subqueries()
        statement = (
            select(Asset, tags_subquery.c.tags, faces_subquery.c.faces)
            .where(Asset.id.in_(asset_ids))
            .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
            .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
            .order_by(ordering)
        )
        return list(self.session.exec(statement).all())

    def _asset_relations_subqueries(self) -> tuple[Any, Any]:
        tags_subquery = (
            select(
                AssetTag.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Tag.id,
                        "name",
                        Tag.name,
                        "path",
                        Tag.path,
                    )
                ).label("tags"),
            )
            .select_from(AssetTag)
            .join(Tag, Tag.id == AssetTag.tag_id)
            .group_by(AssetTag.asset_id)
            .subquery()
        )

        faces_subquery = (
            select(
                Face.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Face.id,
                        "person_id",
                        Person.id,
                        "person_name",
                        Person.name,
                    )
                ).label("faces"),
            )
            .select_from(Face)
            .join(Person, Person.id == Face.person_id, isouter=True)
            .where(Face.is_excluded.is_(False))
            .group_by(Face.asset_id)
            .subquery()
        )
        return tags_subquery, faces_subquery

    @staticmethod
    def _thumbnail_candidate_from_row(
        row: Any,
    ) -> PersonThumbnailCandidate | None:
        if row is None:
            return None
        face_id, asset_id, master_path, mime_type, bounding_box, confidence = row
        if (
            asset_id is None
            or not isinstance(master_path, str)
            or not isinstance(mime_type, str)
            or not isinstance(bounding_box, dict)
        ):
            return None
        return PersonThumbnailCandidate(
            face_id=face_id,
            asset_id=asset_id,
            master_path=master_path,
            mime_type=mime_type,
            bounding_box=bounding_box,
            confidence=confidence,
        )
