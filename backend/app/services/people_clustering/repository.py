from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlmodel import Session, select

from app.models import Face, Person


@dataclass(frozen=True)
class FaceClusterCandidate:
    id: UUID
    face_model_id: int
    confidence: float | None
    crop_path: str | None


class PeopleClusteringRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_cluster_candidates(self, *, model_id: int) -> list[FaceClusterCandidate]:
        statement = (
            select(Face.id, Face.face_model_id, Face.confidence, Face.crop_path)
            .where(
                Face.embedding.is_not(None),
                Face.is_excluded.is_(False),
                Face.is_confirmed.is_(False),
                Face.person_id.is_(None),
                Face.face_model_id == model_id,
            )
            .order_by(Face.created_at.asc(), Face.id.asc())
        )
        rows = self.session.exec(statement).all()
        return [
            FaceClusterCandidate(
                id=row[0],
                face_model_id=row[1],
                confidence=row[2],
                crop_path=row[3],
            )
            for row in rows
        ]

    def list_neighbor_face_ids(
        self,
        *,
        face_id: UUID,
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> list[UUID]:
        statement = sa.text(
            """
            SELECT other.id
            FROM faces AS seed
            JOIN faces AS other
              ON other.id <> seed.id
            WHERE seed.id = :face_id
              AND other.embedding IS NOT NULL
              AND other.is_excluded = false
              AND other.is_confirmed = false
              AND other.person_id IS NULL
              AND other.face_model_id = :model_id
              AND (other.embedding <=> seed.embedding) <= :distance_threshold
            ORDER BY other.embedding <=> seed.embedding ASC, other.id ASC
            LIMIT :top_k
            """
        )
        result = self.session.exec(
            statement.bindparams(
                face_id=face_id,
                model_id=model_id,
                distance_threshold=distance_threshold,
                top_k=top_k,
            )
        )
        return [row[0] for row in result.all()]

    def list_labeled_neighbor_people(
        self,
        *,
        face_id: UUID,
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> list[tuple[UUID, float]]:
        statement = sa.text(
            """
            SELECT other.person_id, CAST(other.embedding <=> seed.embedding AS double precision) AS distance
            FROM faces AS seed
            JOIN faces AS other
              ON other.id <> seed.id
            JOIN people AS person
              ON person.id = other.person_id
            WHERE seed.id = :face_id
              AND other.embedding IS NOT NULL
              AND other.is_excluded = false
              AND other.person_id IS NOT NULL
              AND other.face_model_id = :model_id
              AND person.name IS NOT NULL
              AND btrim(person.name) <> ''
              AND (other.embedding <=> seed.embedding) <= :distance_threshold
            ORDER BY other.embedding <=> seed.embedding ASC, other.id ASC
            LIMIT :top_k
            """
        )
        result = self.session.exec(
            statement.bindparams(
                face_id=face_id,
                model_id=model_id,
                distance_threshold=distance_threshold,
                top_k=top_k,
            )
        )
        return [(row[0], float(row[1])) for row in result.all()]

    def create_person(self) -> Person:
        person = Person(name=None, thumbnail_face_id=None, is_hidden=False)
        self.session.add(person)
        self.session.commit()
        self.session.refresh(person)
        return person

    def assign_faces_to_person(self, *, face_ids: list[UUID], person_id: UUID) -> int:
        if not face_ids:
            return 0
        statement = (
            sa.update(Face)
            .where(Face.id.in_(face_ids))
            .values(person_id=person_id)
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount or 0

    def set_person_thumbnail_face(
        self,
        *,
        person_id: UUID,
        thumbnail_face_id: UUID | None,
    ) -> None:
        statement = (
            sa.update(Person)
            .where(Person.id == person_id)
            .values(thumbnail_face_id=thumbnail_face_id)
        )
        self.session.exec(statement)
        self.session.commit()
