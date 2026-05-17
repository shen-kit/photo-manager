from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel import SQLModel

from app.core.auth import get_current_user
from app.models import User
from app.services.notifications.schemas import NotificationRead
from app.services.notifications.service import (
    NotificationService,
    get_notification_service,
)
from app.services.notifications.types import NotificationCategory, NotificationLevel

router = APIRouter()


class MarkAllReadResponse(SQLModel):
    updated_count: int


@router.get("", response_model=list[NotificationRead], include_in_schema=False)
@router.get("/", response_model=list[NotificationRead])
def list_notifications(
    level: NotificationLevel | None = Query(default=None),
    category: NotificationCategory | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> list[NotificationRead]:
    del current_user
    notifications = notification_service.list_notifications(
        level=level,
        category=category,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return [
        NotificationRead.model_validate(notification, from_attributes=True)
        for notification in notifications
    ]


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationRead:
    del current_user
    notification = notification_service.mark_read(notification_id)
    return NotificationRead.model_validate(notification, from_attributes=True)


@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_notifications_read(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> MarkAllReadResponse:
    del current_user
    updated_count = notification_service.mark_all_read()
    return MarkAllReadResponse(updated_count=updated_count)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    notification_service.delete_notification(notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_notifications(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    notification_service.delete_all_notifications()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
