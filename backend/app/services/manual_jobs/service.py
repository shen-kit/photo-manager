from __future__ import annotations

from math import ceil
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.models import Job
from app.services.jobs.dispatcher import (
    INTENT_BACKFILL,
    INTENT_MAINTENANCE,
    INTENT_METADATA,
)
from app.services.jobs.queue import (
    enqueue_manual_job_batch,
    enqueue_manual_job_run,
)
from app.services.jobs.schemas import JobChildCounts, JobDetailRead, JobRead
from app.services.jobs.service import JobService
from app.services.manual_jobs.catalog import create_manual_job_handlers
from app.services.manual_jobs.schemas import (
    ManualJobCatalogRead,
    ManualJobDefinitionRead,
    ManualJobParameterRead,
    ManualJobRunRequest,
)


class ManualJobService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)
        self.handlers = create_manual_job_handlers(session)

    def list_available_jobs(self) -> ManualJobCatalogRead:
        items: list[ManualJobDefinitionRead] = []
        for handler in self.handlers.values():
            default_payload = handler.default_payload()
            active_job = self.job_service.find_active_job_by_key(
                job_key=handler.definition.job_key
            )
            latest_job = self.job_service.get_latest_visible_job_by_key(
                job_key=handler.definition.job_key
            )
            try:
                pending_count = handler.count_candidates(default_payload)
            except Exception:
                pending_count = None
            items.append(
                ManualJobDefinitionRead(
                    job_key=handler.definition.job_key,
                    title=handler.definition.title,
                    description=handler.definition.description,
                    category=handler.definition.category,
                    mode=handler.definition.mode,
                    supports_dry_run=handler.definition.supports_dry_run,
                    batch_size=handler.definition.batch_size,
                    pending_count=pending_count,
                    active_job_id=active_job.id if active_job else None,
                    active_status=active_job.status if active_job else None,
                    last_job_id=latest_job.id if latest_job else None,
                    last_status=latest_job.status if latest_job else None,
                    last_finished_at=latest_job.finished_at if latest_job else None,
                    parameters=[
                        ManualJobParameterRead(
                            name=parameter.name,
                            type=parameter.type,
                            required=parameter.required,
                            default=parameter.default,
                            description=parameter.description,
                            minimum=parameter.minimum,
                            maximum=parameter.maximum,
                            step=parameter.step,
                        )
                        for parameter in handler.parameters
                    ],
                    default_params=default_payload,
                )
            )
        return ManualJobCatalogRead(items=items)

    async def run_manual_job(
        self,
        *,
        job_key: str,
        request: ManualJobRunRequest | None,
        requested_by_user_id: UUID | None = None,
    ) -> Job:
        handler = self.handlers.get(job_key)
        if handler is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manual job not found",
            )
        active_job = self.job_service.find_active_job_by_key(job_key=job_key)
        if active_job is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Manual job already active",
                    "job_key": job_key,
                    "active_job_id": str(active_job.id),
                },
            )
        request_params = (
            request.params if request is not None and request.params else {}
        )
        normalized_payload = handler.validate_payload(dict(request_params))
        normalized_payload = handler.inject_internal_payload(
            normalized_payload,
            requested_by_user_id=requested_by_user_id,
        )
        parent_job = self.job_service.create_job(
            self._parent_job_type(job_key),
            parameters=normalized_payload or None,
            job_key=job_key,
            is_visible=True,
        )
        if handler.definition.execution_backend == "worker":
            queued = await enqueue_manual_job_run(
                parent_job.id,
                job_key=parent_job.job_key,
                intent=self._dispatch_intent(parent_job.job_key),
            )
            if not queued:
                self.job_service.fail_job(parent_job.id, "Failed to enqueue manual job")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Failed to enqueue manual job",
                )
        return parent_job

    async def execute_parent_job(self, *, job_id: UUID) -> None:
        parent_job = self.job_service.get_job(job_id)
        if parent_job.parent_job_id is not None:
            raise RuntimeError("execute_parent_job requires a parent job")
        if parent_job.job_key is None:
            raise RuntimeError("Manual job parent is missing job_key")
        handler = self.handlers[parent_job.job_key]
        payload = dict(parent_job.parameters or {})
        prepared_run = handler.prepare_run(payload)
        if prepared_run.progress_total is not None:
            self.job_service.update_progress(
                parent_job.id, total=prepared_run.progress_total
            )
        if prepared_run.progress_total == 0:
            self.job_service.complete_job(
                parent_job.id,
                result=handler.build_zero_result(prepared_run.payload),
                message="No candidates found",
            )
            return
        await handler.run_parent_job(parent_job, prepared_run)
        if handler.definition.mode == "global":
            return
        batch_size = handler.definition.batch_size or 100
        candidate_ids = prepared_run.candidate_ids or []
        batch_count = ceil(len(candidate_ids) / batch_size) if candidate_ids else 0
        self.job_service.mark_running(
            parent_job.id,
            message=f"Scheduled {batch_count} batches for {len(candidate_ids)} assets",
        )
        for index in range(0, len(candidate_ids), batch_size):
            batch_asset_ids = candidate_ids[index : index + batch_size]
            queued = await enqueue_manual_job_batch(
                parent_job.id,
                parent_job.job_key,
                prepared_run.payload,
                batch_asset_ids,
                intent=self._dispatch_intent(parent_job.job_key),
            )
            if not queued:
                for asset_id in batch_asset_ids:
                    child = self.job_service.create_job(
                        f"{parent_job.job_key}_asset",
                        parameters={"asset_id": str(asset_id)},
                        job_key=parent_job.job_key,
                        parent_job_id=parent_job.id,
                        related_asset_id=asset_id,
                        is_visible=False,
                    )
                    self.job_service.fail_job(
                        child.id,
                        "Failed to enqueue batch scheduler",
                        result={"asset_id": str(asset_id), "skipped": False},
                    )
                    self.on_child_job_terminal(child.id)

    async def execute_batch(
        self,
        *,
        parent_job_id: UUID,
        job_key: str,
        payload: dict[str, Any],
        asset_ids: list[UUID],
    ) -> None:
        parent_job = self.job_service.get_job(parent_job_id)
        handler = self.handlers[job_key]
        await handler.schedule_batch(parent_job, payload, asset_ids)

    def on_child_job_terminal(self, child_job_id: UUID) -> None:
        child_job = self.job_service.get_job_or_none(child_job_id)
        if child_job is None or child_job.parent_job_id is None:
            return
        parent_job = self.job_service.get_job_or_none(child_job.parent_job_id)
        if parent_job is None or parent_job.job_key is None:
            return
        terminal_count = self.job_service.count_terminal_children(
            parent_job_id=parent_job.id
        )
        child_counts = self.job_service.get_child_counts(parent_job_id=parent_job.id)
        self.job_service.update_progress(
            parent_job.id,
            current=terminal_count,
            message=(
                f"Processed {terminal_count}/{parent_job.progress_total or 0} assets"
            ),
        )
        if (
            parent_job.progress_total is None
            or terminal_count < parent_job.progress_total
        ):
            return
        handler = self.handlers[parent_job.job_key]
        result = handler.build_parent_result(parent_job)
        if child_counts["failed"] > 0:
            self.job_service.fail_job(
                parent_job.id,
                "Manual job completed with failures",
                result=result,
            )
        else:
            self.job_service.complete_job(
                parent_job.id,
                result=result,
                message="Manual job completed",
            )

    def build_job_detail(
        self, job_id: UUID, *, include_children: bool
    ) -> JobDetailRead:
        job = self.job_service.get_job(job_id)
        child_counts = None
        children: list[JobRead] = []
        if job.parent_job_id is None:
            raw_counts = self.job_service.get_child_counts(parent_job_id=job.id)
            if raw_counts["total"] > 0:
                child_counts = JobChildCounts(**raw_counts)
            if include_children:
                children = [
                    JobRead.model_validate(child, from_attributes=True)
                    for child in self.job_service.list_child_jobs(parent_job_id=job.id)
                ]
        return JobDetailRead(
            **JobRead.model_validate(job, from_attributes=True).model_dump(),
            child_counts=child_counts,
            children=children,
        )

    @staticmethod
    def _parent_job_type(job_key: str) -> str:
        return f"manual_job:{job_key}"

    @staticmethod
    def _dispatch_intent(job_key: str | None) -> str:
        if job_key == "bulk_scan":
            return INTENT_METADATA
        if job_key in {
            "run_missing_or_outdated_clip_embeddings",
            "run_missing_or_outdated_face_recognition",
            "regenerate_missing_asset_thumbnails",
            "cluster_faces",
        }:
            return INTENT_BACKFILL
        return INTENT_MAINTENANCE


def get_manual_job_service(
    session: Session = Depends(get_session),
) -> ManualJobService:
    return ManualJobService(session=session)
