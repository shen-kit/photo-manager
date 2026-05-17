from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.models import Notification, utc_now
from app.services.notifications.types import NotificationCategory, NotificationLevel


class NotificationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_notification(
        self,
        level: NotificationLevel,
        category: NotificationCategory,
        title: str,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        related_job_id: UUID | None = None,
        related_asset_id: UUID | None = None,
    ) -> Notification:
        notification = Notification(
            level=level,
            category=category,
            title=title,
            message=message,
            details=details,
            related_job_id=related_job_id,
            related_asset_id=related_asset_id,
        )
        self.session.add(notification)
        self.session.commit()
        self.session.refresh(notification)
        return notification

    def list_notifications(
        self,
        *,
        level: NotificationLevel | None = None,
        category: NotificationCategory | None = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if level is not None:
            statement = statement.where(Notification.level == level)
        if category is not None:
            statement = statement.where(Notification.category == category)
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        return list(self.session.exec(statement).all())

    def mark_read(self, notification_id: UUID) -> Notification:
        notification = self._get_notification(notification_id)
        notification.read_at = utc_now()
        self.session.add(notification)
        self.session.commit()
        self.session.refresh(notification)
        return notification

    def mark_all_read(self) -> int:
        notifications = self.session.exec(
            select(Notification).where(Notification.read_at.is_(None))
        ).all()
        now = utc_now()
        for notification in notifications:
            notification.read_at = now
            self.session.add(notification)
        self.session.commit()
        return len(notifications)

    def delete_notification(self, notification_id: UUID) -> None:
        notification = self._get_notification(notification_id)
        self.session.delete(notification)
        self.session.commit()

    def delete_all_notifications(self) -> int:
        notifications = self.session.exec(select(Notification)).all()
        deleted_count = len(notifications)
        for notification in notifications:
            self.session.delete(notification)
        self.session.commit()
        return deleted_count

    def _get_notification(self, notification_id: UUID) -> Notification:
        notification = self.session.get(Notification, notification_id)
        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )
        return notification


def get_notification_service(
    session: Session = Depends(get_session),
) -> NotificationService:
    return NotificationService(session=session)
