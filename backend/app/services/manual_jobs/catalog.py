from __future__ import annotations

from sqlmodel import Session

from app.services.manual_jobs.handlers import (
    MANUAL_JOB_HANDLER_TYPES,
    ManualJobDefinition,
    ManualJobHandler,
)


def create_manual_job_handlers(session: Session) -> dict[str, ManualJobHandler]:
    handlers: dict[str, ManualJobHandler] = {}
    for handler_type in MANUAL_JOB_HANDLER_TYPES:
        handler = handler_type(session)
        handlers[handler.definition.job_key] = handler
    return handlers


def list_manual_job_definitions(session: Session) -> list[ManualJobDefinition]:
    return [
        handler.definition for handler in create_manual_job_handlers(session).values()
    ]
