from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models import Asset, Face


class FaceQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_active_asset(self, asset_id: UUID) -> Asset:
        asset = self.session.exec(
            select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        ).first()
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        return asset

    def list_faces_for_asset(self, asset_id: UUID) -> list[Face]:
        self.require_active_asset(asset_id)
        statement = (
            select(Face)
            .where(Face.asset_id == asset_id)
            .order_by(Face.created_at.asc(), Face.id.asc())
        )
        return list(self.session.exec(statement).all())


def get_face_query_service(
    session: Session = Depends(get_session),
) -> FaceQueryService:
    return FaceQueryService(session)
