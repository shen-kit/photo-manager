from __future__ import annotations

import os

from arq import run_worker
from arq.connections import RedisSettings

from app.core.logging import setup_logging
from .tasks import (
    generate_asset_clip_embedding,
    generate_missing_asset_clip_embeddings,
    process_asset_metadata,
    scan_originals_library,
)


class WorkerSettings:
    functions = [
        process_asset_metadata,
        scan_originals_library,
        generate_asset_clip_embedding,
        generate_missing_asset_clip_embeddings,
    ]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    queue_name = "arq:queue"


def main() -> None:
    setup_logging()
    run_worker(WorkerSettings)
