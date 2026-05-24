from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections.abc import Iterable

from arq.connections import RedisSettings
from arq.worker import Worker
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.logging import setup_logging
from app.services.jobs.dispatcher import redis_queue_name
from .tasks import (
    generate_asset_clip_embedding,
    generate_asset_clip_embedding_batch,
    generate_asset_preview,
    process_asset_faces,
    process_asset_faces_batch,
    process_asset_metadata,
    process_asset_thumbnail_batch,
    run_manual_job,
    run_system_integrity_diagnostic,
    run_system_integrity_repair,
    schedule_manual_job_batch,
)

logger = logging.getLogger(__name__)
WORKER_RETRY_DELAY_SECONDS = 3.0
DEFAULT_QUEUES = ("interactive", "metadata", "preview", "ai", "backfill", "maintenance")
WORKER_FUNCTIONS = [
    process_asset_metadata,
    generate_asset_preview,
    generate_asset_clip_embedding,
    generate_asset_clip_embedding_batch,
    process_asset_faces,
    process_asset_faces_batch,
    process_asset_thumbnail_batch,
    run_manual_job,
    run_system_integrity_diagnostic,
    run_system_integrity_repair,
    schedule_manual_job_batch,
]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    return max(value, 1)


def configured_queues() -> list[str]:
    raw = os.getenv("WORKER_QUEUES")
    if not raw:
        return list(DEFAULT_QUEUES)
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_shared_ctx() -> dict[str, object]:
    total_concurrency = _env_int("WORKER_TOTAL_CONCURRENCY", _env_int("WORKER_MAX_JOBS", 1))
    return {
        "worker_semaphore": asyncio.Semaphore(total_concurrency),
        "preview_semaphore": asyncio.Semaphore(
            _env_int("WORKER_PREVIEW_CONCURRENCY", total_concurrency)
        ),
        "video_preview_semaphore": asyncio.Semaphore(
            _env_int("WORKER_VIDEO_PREVIEW_CONCURRENCY", 1)
        ),
        "clip_semaphore": asyncio.Semaphore(_env_int("WORKER_CLIP_CONCURRENCY", 1)),
        "faces_semaphore": asyncio.Semaphore(_env_int("WORKER_FACES_CONCURRENCY", 1)),
        "face_clustering_semaphore": asyncio.Semaphore(
            _env_int("WORKER_FACE_CLUSTERING_CONCURRENCY", 1)
        ),
        "scan_semaphore": asyncio.Semaphore(_env_int("WORKER_SCAN_CONCURRENCY", 1)),
        "maintenance_semaphore": asyncio.Semaphore(
            _env_int("WORKER_MAINTENANCE_CONCURRENCY", 1)
        ),
    }


def build_workers(
    *,
    queues: Iterable[str] | None = None,
    ctx: dict[str, object] | None = None,
) -> list[Worker]:
    selected_queues = list(queues or configured_queues())
    shared_ctx = ctx or build_shared_ctx()
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    max_jobs = _env_int("WORKER_MAX_JOBS", 1)
    workers: list[Worker] = []
    for queue_name in selected_queues:
        workers.append(
            Worker(
                WORKER_FUNCTIONS,
                queue_name=redis_queue_name(queue_name),
                redis_settings=redis_settings,
                handle_signals=False,
                max_jobs=max_jobs,
                queue_read_limit=max_jobs,
                ctx=dict(shared_ctx),
                health_check_key=f"arq:health:{queue_name}",
            )
        )
    return workers


async def _close_workers(workers: list[Worker]) -> None:
    for worker in workers:
        try:
            await worker.close()
        except Exception:
            logger.exception("Failed to close worker for queue %s", worker.queue_name)


async def async_main() -> None:
    workers = build_workers()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _shutdown(signum: signal.Signals) -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        for worker in workers:
            worker.handle_sig(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, _shutdown, signum)
        except NotImplementedError:
            continue

    tasks = [asyncio.create_task(worker.async_run()) for worker in workers]
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, pending = await asyncio.wait(
            [*tasks, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            await asyncio.gather(*tasks, return_exceptions=True)
            return
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
    finally:
        stop_task.cancel()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await _close_workers(workers)


def main() -> None:
    setup_logging()
    while True:
        try:
            asyncio.run(async_main())
            return
        except KeyboardInterrupt:
            return
        except (RedisTimeoutError, RedisConnectionError, OSError) as exc:
            logger.warning(
                "Worker failed to connect to Redis; retrying in %.1f seconds: %s",
                WORKER_RETRY_DELAY_SECONDS,
                exc,
            )
            time.sleep(WORKER_RETRY_DELAY_SECONDS)
