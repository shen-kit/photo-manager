from __future__ import annotations

import os

from arq import run_worker
from arq.connections import RedisSettings

from app.core.logging import setup_logging
from .tasks import (
    generate_asset_clip_embedding,
    process_asset_metadata,
    process_asset_faces,
    run_manual_job,
    schedule_manual_job_batch,
)


class WorkerSettings:
    functions = [
        process_asset_metadata,
        generate_asset_clip_embedding,
        process_asset_faces,
        run_manual_job,
        schedule_manual_job_batch,
    ]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    queue_name = "arq:queue"


def main() -> None:
    setup_logging()
    run_worker(WorkerSettings)
