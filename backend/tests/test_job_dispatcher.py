from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from contextlib import nullcontext

sys.modules.setdefault("open_clip", types.ModuleType("open_clip"))
if "torch" not in sys.modules:
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch_stub.nn = types.SimpleNamespace(Module=object)
    torch_stub.autocast = lambda *args, **kwargs: nullcontext()
    torch_stub.inference_mode = lambda: nullcontext()
    sys.modules["torch"] = torch_stub

from app.models import Job
from app.services.jobs.dispatcher import (
    GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
    GENERATE_ASSET_PREVIEW_JOB_NAME,
    INTENT_AI,
    INTENT_BACKFILL,
    INTENT_INTERACTIVE,
    INTENT_MAINTENANCE,
    INTENT_METADATA,
    RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
    RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
    JobDispatcher,
    clip_dedup_key,
    faces_dedup_key,
    preview_dedup_key,
    queue_for_task,
)
from worker.settings import build_shared_ctx, build_workers, configured_queues


def _job(
    *,
    queue_name: str | None = None,
    dedup_key: str | None = None,
    parameters: dict[str, object] | None = None,
) -> Job:
    return Job(
        id=uuid4(),
        type="test_job",
        status="queued",
        queue_name=queue_name,
        dedup_key=dedup_key,
        parameters=parameters,
        progress_current=0,
        is_visible=False,
        created_at=datetime.now(timezone.utc),
    )


class _FakeSession:
    def add(self, value) -> None:
        del value

    def commit(self) -> None:
        return None

    def refresh(self, value) -> None:
        del value


class _FakeJobService:
    active_job: Job | None = None
    created_jobs: list[Job] = []

    def __init__(self, session) -> None:
        del session

    def find_active_job_by_dedup_key(self, *, dedup_key: str) -> Job | None:
        del dedup_key
        return self.active_job

    def create_job(self, type: str, **kwargs) -> Job:
        job = _job(
            queue_name=kwargs.get("queue_name"),
            dedup_key=kwargs.get("dedup_key"),
            parameters=kwargs.get("parameters"),
        )
        job.type = type
        self.created_jobs.append(job)
        return job

    def get_job(self, job_id):
        for job in self.created_jobs:
            if job.id == job_id:
                return job
        raise AssertionError(job_id)

    def fail_job(self, job_id, message):
        raise AssertionError((job_id, message))


class JobDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeJobService.active_job = None
        _FakeJobService.created_jobs = []

    def test_queue_routing_matches_intent(self) -> None:
        self.assertEqual(
            queue_for_task(
                job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
                intent=INTENT_INTERACTIVE,
            ),
            "interactive",
        )
        self.assertEqual(
            queue_for_task(
                job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
                intent=INTENT_BACKFILL,
            ),
            "backfill",
        )
        self.assertEqual(
            queue_for_task(
                job_name=GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
                intent=INTENT_AI,
            ),
            "ai",
        )
        self.assertEqual(
            queue_for_task(
                job_name="run_manual_job",
                intent=INTENT_MAINTENANCE,
            ),
            "maintenance",
        )
        self.assertEqual(
            queue_for_task(
                job_name="run_manual_job",
                intent=INTENT_METADATA,
            ),
            "metadata",
        )
        self.assertEqual(
            queue_for_task(
                job_name=RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
                intent=INTENT_MAINTENANCE,
            ),
            "maintenance",
        )
        self.assertEqual(
            queue_for_task(
                job_name=RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
                intent=INTENT_MAINTENANCE,
            ),
            "maintenance",
        )

    def test_dedup_keys_include_asset_and_model_scope(self) -> None:
        asset_id = uuid4()
        self.assertEqual(preview_dedup_key(asset_id), f"preview:{asset_id}")
        self.assertEqual(clip_dedup_key(asset_id, model_id=7), f"clip:{asset_id}:7")
        self.assertEqual(
            faces_dedup_key(asset_id, model_id=9, auto_match=True),
            f"faces:{asset_id}:9:1",
        )

    def test_dispatch_reuses_existing_active_job(self) -> None:
        existing = _job(queue_name="preview", dedup_key="preview:key")
        _FakeJobService.active_job = existing

        with patch("app.services.jobs.dispatcher.JobService", _FakeJobService):
            dispatcher = JobDispatcher(_FakeSession())
            dispatcher._enqueue = AsyncMock()
            result = self._run_async(
                dispatcher.dispatch(
                    job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
                    args=["asset-id", None, "low"],
                    type=GENERATE_ASSET_PREVIEW_JOB_NAME,
                    parameters={"asset_id": "asset-id", "priority": "low"},
                    intent="preview",
                    dedup_key="preview:key",
                    force=False,
                )
            )

        self.assertTrue(result.reused_existing)
        self.assertEqual(result.job.id, existing.id)
        dispatcher._enqueue.assert_not_called()

    def test_dispatch_allows_urgent_duplicate_on_different_queue(self) -> None:
        existing = _job(queue_name="preview", dedup_key="preview:key")
        _FakeJobService.active_job = existing

        with patch("app.services.jobs.dispatcher.JobService", _FakeJobService):
            dispatcher = JobDispatcher(_FakeSession())
            dispatcher._enqueue = AsyncMock(return_value=True)
            result = self._run_async(
                dispatcher.dispatch(
                    job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
                    args=["asset-id", None, "high"],
                    type=GENERATE_ASSET_PREVIEW_JOB_NAME,
                    parameters={"asset_id": "asset-id", "priority": "high"},
                    intent=INTENT_INTERACTIVE,
                    dedup_key="preview:key",
                    force=False,
                    allow_active_duplicate=True,
                )
            )

        self.assertTrue(result.created)
        self.assertFalse(result.reused_existing)
        self.assertEqual(result.job.queue_name, "interactive")
        self.assertEqual(
            result.job.parameters["supersedes_job_id"],
            str(existing.id),
        )

    @staticmethod
    def _run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)


class WorkerSettingsTest(unittest.TestCase):
    def test_configured_queues_reads_env(self) -> None:
        with patch.dict(os.environ, {"WORKER_QUEUES": "interactive,preview"}, clear=False):
            self.assertEqual(configured_queues(), ["interactive", "preview"])

    def test_build_workers_uses_queue_specific_names(self) -> None:
        ctx = build_shared_ctx()

        with patch.dict(
            os.environ,
            {
                "WORKER_MAX_JOBS": "2",
                "WORKER_TOTAL_CONCURRENCY": "2",
            },
            clear=False,
        ):
            workers = build_workers(queues=["interactive", "preview"], ctx=ctx)
        for worker in workers:
            self.addCleanup(worker.loop.close)

        self.assertEqual(
            [worker.queue_name for worker in workers],
            ["arq:queue:interactive", "arq:queue:preview"],
        )
        self.assertIs(
            workers[0].ctx["worker_semaphore"],
            workers[1].ctx["worker_semaphore"],
        )
        self.assertEqual(workers[0].max_jobs, 2)


if __name__ == "__main__":
    unittest.main()
