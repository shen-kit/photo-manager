from __future__ import annotations

import logging
import os
import time

from arq import run_worker
from arq.connections import RedisSettings
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.logging import setup_logging
from .tasks import (
    generate_asset_clip_embedding,
    generate_asset_clip_embedding_batch,
    generate_asset_preview,
    process_asset_metadata,
    process_asset_thumbnail_batch,
    process_asset_faces,
    process_asset_faces_batch,
    run_manual_job,
    schedule_manual_job_batch,
)

logger = logging.getLogger(__name__)
WORKER_RETRY_DELAY_SECONDS = 3.0


class WorkerSettings:
    functions = [
        process_asset_metadata,
        generate_asset_preview,
        generate_asset_clip_embedding,
        generate_asset_clip_embedding_batch,
        process_asset_faces,
        process_asset_faces_batch,
        process_asset_thumbnail_batch,
        run_manual_job,
        schedule_manual_job_batch,
    ]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    queue_name = "arq:queue"


def main() -> None:
    setup_logging()
    while True:
        try:
            run_worker(WorkerSettings)
            return
        except (RedisTimeoutError, RedisConnectionError, OSError) as exc:
            logger.warning(
                "Worker failed to connect to Redis; retrying in %.1f seconds: %s",
                WORKER_RETRY_DELAY_SECONDS,
                exc,
            )
            time.sleep(WORKER_RETRY_DELAY_SECONDS)
