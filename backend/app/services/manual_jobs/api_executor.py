from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from sqlmodel import Session

from app.core.database import engine
from app.services.jobs.service import JobService
from app.services.manual_jobs.catalog import create_manual_job_handlers
from app.services.manual_jobs.service import ManualJobService

logger = logging.getLogger(__name__)
API_MANUAL_JOB_POLL_INTERVAL_SECONDS = 2.0


class ApiManualJobExecutor:
    def __init__(self) -> None:
        self._api_job_keys = self._load_api_job_keys()

    async def run_forever(self, *, stop_event: asyncio.Event) -> None:
        self._fail_stale_running_jobs()
        while not stop_event.is_set():
            executed = await self._run_next_job()
            if executed:
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=API_MANUAL_JOB_POLL_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue

    def _load_api_job_keys(self) -> tuple[str, ...]:
        with Session(engine) as session:
            handlers = create_manual_job_handlers(session)
            return tuple(
                handler.definition.job_key
                for handler in handlers.values()
                if handler.definition.execution_backend == "api"
            )

    def _fail_stale_running_jobs(self) -> None:
        if not self._api_job_keys:
            return
        with Session(engine) as session:
            job_service = JobService(session)
            for job_key in self._api_job_keys:
                jobs = job_service.list_root_jobs_by_key_and_status(
                    job_key=job_key,
                    statuses=("running",),
                )
                for job in jobs:
                    job_service.fail_job(
                        job.id,
                        (
                            f"{job_key} was interrupted; rerun is safe and will "
                            "reconcile filesystem and database state"
                        ),
                        result=job.result,
                    )

    async def _run_next_job(self) -> bool:
        for job_key in self._api_job_keys:
            claimed_job_id = self._claim_oldest_queued_job(job_key)
            if claimed_job_id is None:
                continue
            await self._execute_job(claimed_job_id)
            return True
        return False

    def _claim_oldest_queued_job(self, job_key: str):
        with Session(engine) as session:
            job_service = JobService(session)
            queued_jobs = job_service.list_root_jobs_by_key_and_status(
                job_key=job_key,
                statuses=("queued",),
            )
            for job in queued_jobs:
                if job_service.claim_queued_job(job.id, message=f"Starting {job_key}"):
                    return job.id
        return None

    async def _execute_job(self, job_id) -> None:
        try:
            with Session(engine) as session:
                await ManualJobService(session).execute_parent_job(job_id=job_id)
        except Exception:
            logger.exception("API manual job %s failed unexpectedly", job_id)
            with Session(engine) as session:
                JobService(session).fail_job(
                    job_id,
                    "Manual job failed unexpectedly",
                )
