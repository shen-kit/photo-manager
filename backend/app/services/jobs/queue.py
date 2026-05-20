from __future__ import annotations

import logging
import os
from uuid import UUID

from arq.connections import RedisSettings, create_pool

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)

PROCESS_ASSET_METADATA_JOB_NAME = "process_asset_metadata"
GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME = "generate_asset_clip_embedding"
PROCESS_ASSET_FACES_JOB_NAME = "process_asset_faces"
RUN_MANUAL_JOB_NAME = "run_manual_job"
SCHEDULE_MANUAL_JOB_BATCH_NAME = "schedule_manual_job_batch"


async def enqueue_worker_job(job_name: str, *args: object) -> bool:
    try:
        redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        try:
            await redis.enqueue_job(job_name, *args)
        finally:
            await redis.aclose()
    except Exception:
        logger.exception("Failed to enqueue job %s", job_name)
        return False
    return True


async def enqueue_asset_processing_job(
    asset_id: UUID,
    job_id: UUID | None = None,
    *,
    parent_job_id: UUID | None = None,
    enqueue_embedding: bool = True,
    enqueue_faces: bool = True,
) -> bool:
    args: list[object] = [
        str(asset_id),
        str(job_id) if job_id is not None else None,
        str(parent_job_id) if parent_job_id is not None else None,
        enqueue_embedding,
        enqueue_faces,
    ]
    return await enqueue_worker_job(PROCESS_ASSET_METADATA_JOB_NAME, *args)


async def enqueue_asset_embedding_job(
    asset_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
) -> bool:
    args: list[object] = [str(asset_id), force]
    if job_id is not None:
        args.append(str(job_id))
    return await enqueue_worker_job(GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME, *args)


async def enqueue_asset_faces_job(
    asset_id: UUID,
    *,
    force: bool = False,
    auto_match: bool = True,
    job_id: UUID | None = None,
) -> bool:
    args: list[object] = [str(asset_id), force, auto_match]
    if job_id is not None:
        args.append(str(job_id))
    return await enqueue_worker_job(PROCESS_ASSET_FACES_JOB_NAME, *args)


async def enqueue_manual_job_run(job_id: UUID) -> bool:
    return await enqueue_worker_job(RUN_MANUAL_JOB_NAME, str(job_id))


async def enqueue_manual_job_batch(
    parent_job_id: UUID,
    job_key: str,
    payload: dict[str, object],
    asset_ids: list[UUID],
) -> bool:
    return await enqueue_worker_job(
        SCHEDULE_MANUAL_JOB_BATCH_NAME,
        str(parent_job_id),
        job_key,
        payload,
        [str(asset_id) for asset_id in asset_ids],
    )
