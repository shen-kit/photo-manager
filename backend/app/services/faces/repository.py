from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Session, col, delete, func, select

from app.models import Asset, Face, Person


class FaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset(self, asset_id: UUID) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def get_face(self, face_id: UUID) -> Face | None:
        return self.session.get(Face, face_id)

    def get_person(self, person_id: UUID) -> Person | None:
        return self.session.get(Person, person_id)

    def asset_has_faces(self, *, asset_id: UUID, model_id: int) -> bool:
        statement = select(Face.id).where(
            Face.asset_id == asset_id,
            Face.face_model_id == model_id,
        )
        return self.session.exec(statement).first() is not None

    def count_faces(self, *, asset_id: UUID, model_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Face)
            .where(
                Face.asset_id == asset_id,
                Face.face_model_id == model_id,
            )
        )
        return int(self.session.exec(statement).one())

    def count_confirmed_faces(self, *, asset_id: UUID, model_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Face)
            .where(
                Face.asset_id == asset_id,
                Face.face_model_id == model_id,
                Face.is_confirmed.is_(True),
            )
        )
        return int(self.session.exec(statement).one())

    def list_confirmed_bounding_boxes(
        self,
        *,
        asset_id: UUID,
        model_id: int,
    ) -> list[dict[str, Any]]:
        statement = select(Face.bounding_box).where(
            Face.asset_id == asset_id,
            Face.face_model_id == model_id,
            Face.is_confirmed.is_(True),
        )
        return [
            box for box in self.session.exec(statement).all() if isinstance(box, dict)
        ]

    def list_protected_bounding_boxes(
        self,
        *,
        asset_id: UUID,
        model_id: int,
    ) -> list[dict[str, Any]]:
        statement = select(Face.bounding_box).where(
            Face.asset_id == asset_id,
            Face.face_model_id == model_id,
            Face.is_confirmed.is_(True) | Face.is_excluded.is_(True),
        )
        return [
            box for box in self.session.exec(statement).all() if isinstance(box, dict)
        ]

    def delete_unconfirmed_faces(self, *, asset_id: UUID, model_id: int) -> int:
        statement = delete(Face).where(
            Face.asset_id == asset_id,
            Face.face_model_id == model_id,
            Face.is_confirmed.is_(False),
            Face.is_excluded.is_(False),
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount or 0

    def insert_faces(self, *, faces: list[Face]) -> None:
        if not faces:
            return
        self.session.add_all(faces)
        self.session.commit()

    def update_face(self, face: Face) -> Face:
        self.session.add(face)
        self.session.commit()
        self.session.refresh(face)
        return face

    def count_assets_pending_face_processing(
        self, *, model_id: int, force: bool
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Asset)
            .where(
                Asset.deleted_at.is_(None),
                col(Asset.mime_type).like("image/%"),
            )
        )
        if not force:
            statement = statement.where(
                ~select(Face.id)
                .where(
                    Face.asset_id == Asset.id,
                    Face.face_model_id == model_id,
                )
                .exists()
            )
        return int(self.session.exec(statement).one())

    def list_asset_ids_pending_face_processing(
        self,
        *,
        model_id: int,
        force: bool,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UUID]:
        statement = (
            select(Asset.id)
            .where(
                Asset.deleted_at.is_(None),
                col(Asset.mime_type).like("image/%"),
            )
            .order_by(Asset.created_at.asc(), Asset.id.asc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        if not force:
            statement = statement.where(
                ~select(Face.id)
                .where(
                    Face.asset_id == Asset.id,
                    Face.face_model_id == model_id,
                )
                .exists()
            )
        return list(self.session.exec(statement).all())
