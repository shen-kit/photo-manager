from __future__ import annotations

import os

from arq import run_worker
from arq.connections import RedisSettings

from app.services.assets_jobs import ingest_asset_path, process_asset_metadata


class WorkerSettings:
    functions = [ingest_asset_path, process_asset_metadata]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    queue_name = "arq:queue"


def main() -> None:
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
