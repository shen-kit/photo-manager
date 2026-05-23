from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings, create_pool
from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.database import engine
from app.models import Job
from app.services.jobs.service import JobService

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)

QUEUE_INTERACTIVE = "interactive"
QUEUE_METADATA = "metadata"
QUEUE_PREVIEW = "preview"
QUEUE_AI = "ai"
QUEUE_BACKFILL = "backfill"
QUEUE_MAINTENANCE = "maintenance"

INTENT_INTERACTIVE = "interactive"
INTENT_METADATA = "metadata"
INTENT_PREVIEW = "preview"
INTENT_AI = "ai"
INTENT_BACKFILL = "backfill"
INTENT_MAINTENANCE = "maintenance"

PROCESS_ASSET_METADATA_JOB_NAME = "process_asset_metadata"
GENERATE_ASSET_PREVIEW_JOB_NAME = "generate_asset_preview"
GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME = "generate_asset_clip_embedding"
PROCESS_ASSET_FACES_JOB_NAME = "process_asset_faces"
PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME = "process_asset_thumbnail_batch"
GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME = "generate_asset_clip_embedding_batch"
PROCESS_ASSET_FACES_BATCH_JOB_NAME = "process_asset_faces_batch"
RUN_MANUAL_JOB_NAME = "run_manual_job"
SCHEDULE_MANUAL_JOB_BATCH_NAME = "schedule_manual_job_batch"


def redis_queue_name(queue_name: str) -> str:
    return f"arq:queue:{queue_name}"


def params_hash(parameters: dict[str, Any] | None) -> str | None:
    if not parameters:
        return None
    payload = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def preview_dedup_key(asset_id: UUID) -> str:
    return f"preview:{asset_id}"


def metadata_dedup_key(
    asset_id: UUID,
    *,
    enqueue_embedding: bool,
    enqueue_faces: bool,
) -> str:
    return f"metadata:{asset_id}:{int(enqueue_embedding)}:{int(enqueue_faces)}"


def clip_dedup_key(asset_id: UUID, *, model_id: int | None = None) -> str:
    model_part = "default" if model_id is None else str(model_id)
    return f"clip:{asset_id}:{model_part}"


def faces_dedup_key(
    asset_id: UUID,
    *,
    model_id: int | None = None,
    auto_match: bool,
) -> str:
    model_part = "default" if model_id is None else str(model_id)
    return f"faces:{asset_id}:{model_part}:{int(auto_match)}"


def thumbnail_batch_dedup_key(
    *,
    asset_ids: list[str],
) -> str:
    payload = ",".join(asset_ids)
    return "thumbnail-batch:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def embedding_batch_dedup_key(
    *,
    asset_ids: list[str],
    force: bool,
) -> str:
    payload = json.dumps(
        {"asset_ids": asset_ids, "force": force},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "clip-batch:" + hashlib.sha256(payload).hexdigest()[:16]


def faces_batch_dedup_key(
    *,
    asset_ids: list[str],
    force: bool,
    auto_match: bool,
) -> str:
    payload = json.dumps(
        {"asset_ids": asset_ids, "force": force, "auto_match": auto_match},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "faces-batch:" + hashlib.sha256(payload).hexdigest()[:16]


def manual_run_dedup_key(job_id: UUID, *, job_key: str | None) -> str:
    return f"manual-run:{job_key or 'unknown'}:{job_id}"


def manual_batch_dedup_key(
    parent_job_id: UUID,
    *,
    job_key: str,
    asset_ids: list[str],
) -> str:
    payload = ",".join(asset_ids)
    return (
        f"manual-batch:{job_key}:{parent_job_id}:"
        + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    )


def queue_for_task(*, job_name: str, intent: str) -> str:
    if job_name == GENERATE_ASSET_PREVIEW_JOB_NAME:
        if intent == INTENT_INTERACTIVE:
            return QUEUE_INTERACTIVE
        if intent == INTENT_BACKFILL:
            return QUEUE_BACKFILL
        return QUEUE_PREVIEW
    if job_name == PROCESS_ASSET_METADATA_JOB_NAME:
        return QUEUE_METADATA
    if job_name in {
        GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME,
        PROCESS_ASSET_FACES_JOB_NAME,
    }:
        return QUEUE_BACKFILL if intent == INTENT_BACKFILL else QUEUE_AI
    if job_name in {
        PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
        GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
        PROCESS_ASSET_FACES_BATCH_JOB_NAME,
    }:
        if job_name == PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME:
            return QUEUE_METADATA if intent == INTENT_METADATA else QUEUE_BACKFILL
        return QUEUE_BACKFILL if intent == INTENT_BACKFILL else QUEUE_AI
    if job_name in {RUN_MANUAL_JOB_NAME, SCHEDULE_MANUAL_JOB_BATCH_NAME}:
        if intent == INTENT_BACKFILL:
            return QUEUE_BACKFILL
        return QUEUE_MAINTENANCE if intent == INTENT_MAINTENANCE else QUEUE_METADATA
    raise RuntimeError(f"Unsupported job name for queue routing: {job_name}")


@dataclass(frozen=True)
class DispatchResult:
    job: Job
    created: bool
    reused_existing: bool


class JobDispatcher:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)

    async def dispatch(
        self,
        *,
        job_name: str,
        args: list[object],
        type: str,
        parameters: dict[str, Any] | None,
        intent: str,
        dedup_key: str | None,
        job_key: str | None = None,
        related_asset_id: UUID | None = None,
        parent_job_id: UUID | None = None,
        is_visible: bool = False,
        force: bool = False,
        allow_active_duplicate: bool = False,
        existing_job: Job | None = None,
        existing_job_id: UUID | None = None,
    ) -> DispatchResult:
        queue_name = queue_for_task(job_name=job_name, intent=intent)
        existing_active = None
        if dedup_key and not force:
            existing_active = self.job_service.find_active_job_by_dedup_key(
                dedup_key=dedup_key
            )
        if (
            existing_active is not None
            and not (
                allow_active_duplicate and existing_active.queue_name != queue_name
            )
        ):
            return DispatchResult(
                job=existing_active,
                created=False,
                reused_existing=True,
            )
        payload_hash = params_hash(parameters)
        job = existing_job
        if job is None and existing_job_id is not None:
            job = self.job_service.get_job(existing_job_id)
        if job is None:
            job = self.job_service.create_job(
                type,
                parameters=parameters,
                job_key=job_key,
                queue_name=queue_name,
                intent=intent,
                dedup_key=dedup_key,
                params_hash=payload_hash,
                parent_job_id=parent_job_id,
                related_asset_id=related_asset_id,
                is_visible=is_visible,
            )
        else:
            job.queue_name = queue_name
            job.intent = intent
            job.dedup_key = dedup_key
            job.params_hash = payload_hash
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
        if existing_active is not None and allow_active_duplicate and existing_active.queue_name != queue_name:
            parameters = dict(parameters or {})
            parameters["supersedes_job_id"] = str(existing_active.id)
            job.parameters = parameters
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
        queued = await self._enqueue(
            job_name=job_name,
            args=args,
            queue_name=queue_name,
            job_id=job.id,
        )
        if not queued:
            self.job_service.fail_job(job.id, f"Failed to enqueue job {job_name}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to enqueue job {job_name}",
            )
        return DispatchResult(job=job, created=True, reused_existing=False)

    async def _enqueue(
        self,
        *,
        job_name: str,
        args: list[object],
        queue_name: str,
        job_id: UUID,
    ) -> bool:
        try:
            redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
            try:
                await redis.enqueue_job(
                    job_name,
                    *args,
                    _job_id=str(job_id),
                    _queue_name=redis_queue_name(queue_name),
                )
            finally:
                await redis.aclose()
        except Exception:
            logger.exception("Failed to enqueue job %s on queue %s", job_name, queue_name)
            return False
        return True


async def dispatch_with_new_session(**kwargs: Any) -> DispatchResult:
    with Session(engine) as session:
        dispatcher = JobDispatcher(session)
        return await dispatcher.dispatch(**kwargs)
