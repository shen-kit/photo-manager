from __future__ import annotations

import logging
import os
from uuid import UUID

from arq.connections import RedisSettings, create_pool

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
logger = logging.getLogger(__name__)

PROCESS_ASSET_METADATA_JOB_NAME = "process_asset_metadata"
SCAN_ORIGINALS_LIBRARY_JOB_NAME = "scan_originals_library"
GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME = "generate_asset_clip_embedding"
GENERATE_MISSING_ASSET_CLIP_EMBEDDINGS_JOB_NAME = (
    "generate_missing_asset_clip_embeddings"
)


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
    asset_id: UUID, job_id: UUID | None = None
) -> bool:
    if job_id is None:
        return await enqueue_worker_job(PROCESS_ASSET_METADATA_JOB_NAME, str(asset_id))
    return await enqueue_worker_job(
        PROCESS_ASSET_METADATA_JOB_NAME,
        str(asset_id),
        str(job_id),
    )


async def enqueue_scan_job(job_id: UUID) -> bool:
    return await enqueue_worker_job(SCAN_ORIGINALS_LIBRARY_JOB_NAME, str(job_id))


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


async def enqueue_missing_asset_embeddings_job(
    job_id: UUID,
    *,
    force: bool = False,
) -> bool:
    return await enqueue_worker_job(
        GENERATE_MISSING_ASSET_CLIP_EMBEDDINGS_JOB_NAME,
        str(job_id),
        force,
    )
