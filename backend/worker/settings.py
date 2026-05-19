from __future__ import annotations

import os

from arq import run_worker
from arq.connections import RedisSettings

from app.core.logging import setup_logging
from .tasks import (
    cluster_faces,
    generate_asset_clip_embedding,
    generate_missing_asset_clip_embeddings,
    generate_missing_asset_faces,
    process_asset_metadata,
    process_asset_faces,
    scan_originals_library,
)


class WorkerSettings:
    functions = [
        process_asset_metadata,
        scan_originals_library,
        generate_asset_clip_embedding,
        generate_missing_asset_clip_embeddings,
        process_asset_faces,
        generate_missing_asset_faces,
        cluster_faces,
    ]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    queue_name = "arq:queue"


def main() -> None:
    setup_logging()
    run_worker(WorkerSettings)
