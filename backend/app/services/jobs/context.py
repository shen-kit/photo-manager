from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel


@dataclass(frozen=True)
class JobNotification:
    level: NotificationLevel
    category: NotificationCategory
    title: str
    message: str
    details: dict[str, Any] | None = None
    related_asset_id: UUID | None = None


class JobTaskContext:
    def __init__(self, session: Session, *, job_id: UUID | None) -> None:
        self.session = session
        self.job_id = job_id
        self.job_service = JobService(session)
        self.notification_service = NotificationService(session)

    def mark_running(self, message: str) -> None:
        if self.job_id is None:
            return
        self.job_service.mark_running(self.job_id, message=message)

    def notify(self, notification: JobNotification) -> None:
        self.notification_service.create_notification(
            level=notification.level,
            category=notification.category,
            title=notification.title,
            message=notification.message,
            details=notification.details,
            related_job_id=self.job_id,
            related_asset_id=notification.related_asset_id,
        )

    def fail(
        self,
        error_message: str,
        *,
        result: dict[str, Any] | None = None,
        notification: JobNotification | None = None,
    ) -> None:
        if notification is not None:
            self.notify(notification)
        if self.job_id is not None:
            self.job_service.fail_job(self.job_id, error_message, result=result)

    def complete(
        self,
        message: str,
        *,
        result: dict[str, Any] | None = None,
        notification: JobNotification | None = None,
    ) -> None:
        if self.job_id is not None:
            self.job_service.complete_job(self.job_id, result=result, message=message)
        if notification is not None:
            self.notify(notification)
