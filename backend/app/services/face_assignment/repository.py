from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlmodel import Session, select

from app.models import Face


@dataclass(frozen=True)
class FaceAssignmentCandidate:
    id: UUID
    asset_id: UUID
    face_model_id: int


@dataclass(frozen=True)
class FaceAssignmentNeighbor:
    person_id: UUID
    distance: float


class FaceAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_assignment_candidates(
        self,
        *,
        asset_id: UUID,
        model_id: int,
    ) -> list[FaceAssignmentCandidate]:
        statement = (
            select(Face.id, Face.asset_id, Face.face_model_id)
            .where(
                Face.asset_id == asset_id,
                Face.embedding.is_not(None),
                Face.person_id.is_(None),
                Face.is_confirmed.is_(False),
                Face.is_excluded.is_(False),
                Face.face_model_id == model_id,
            )
            .order_by(Face.created_at.asc(), Face.id.asc())
        )
        rows = self.session.exec(statement).all()
        return [
            FaceAssignmentCandidate(
                id=row[0],
                asset_id=row[1],
                face_model_id=row[2],
            )
            for row in rows
            if row[1] is not None and row[2] is not None
        ]

    def list_reference_neighbors(
        self,
        *,
        face_id: UUID,
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> list[FaceAssignmentNeighbor]:
        statement = sa.text(
            """
            SELECT other.person_id,
                   CAST(other.embedding <=> seed.embedding AS double precision) AS distance
            FROM faces AS seed
            JOIN faces AS other
              ON other.id <> seed.id
            WHERE seed.id = :face_id
              AND other.embedding IS NOT NULL
              AND other.person_id IS NOT NULL
              AND other.is_excluded = false
              AND other.face_model_id = :model_id
              AND (other.asset_id IS NULL OR other.asset_id <> seed.asset_id)
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
        return [
            FaceAssignmentNeighbor(person_id=row[0], distance=float(row[1]))
            for row in result.all()
        ]

    def assign_face_to_person(self, *, face_id: UUID, person_id: UUID) -> bool:
        statement = (
            sa.update(Face)
            .where(
                Face.id == face_id,
                Face.person_id.is_(None),
                Face.is_confirmed.is_(False),
                Face.is_excluded.is_(False),
            )
            .values(person_id=person_id, updated_at=sa.func.now())
        )
        result = self.session.exec(statement)
        self.session.commit()
        return bool(result.rowcount)
