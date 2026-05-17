from __future__ import annotations

import os

from arq import run_worker
from arq.connections import RedisSettings

from app.core.database import create_db_and_tables
from app.core.logging import setup_logging
from .tasks import process_asset_metadata, scan_originals_library


class WorkerSettings:
    functions = [process_asset_metadata, scan_originals_library]
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    queue_name = "arq:queue"


def main() -> None:
    setup_logging()
    create_db_and_tables()
    run_worker(WorkerSettings)
