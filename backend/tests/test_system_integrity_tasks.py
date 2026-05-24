from __future__ import annotations

import asyncio
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

import sys
import types

sys.modules.setdefault("open_clip", types.ModuleType("open_clip"))
if "torch" not in sys.modules:
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch_stub.nn = types.SimpleNamespace(Module=object)
    torch_stub.autocast = lambda *args, **kwargs: nullcontext()
    torch_stub.inference_mode = lambda: nullcontext()
    sys.modules["torch"] = torch_stub

from app.models import DiagnosticRun
from app.services.system_integrity.tasks import (
    run_system_integrity_diagnostic,
    run_system_integrity_repair,
)


class _SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeJobService:
    def __init__(self, session) -> None:
        del session
        self.running: list[tuple[object, str | None]] = []
        self.completed: list[tuple[object, dict[str, object] | None, str | None]] = []
        self.failed: list[tuple[object, str]] = []

    def mark_running(self, job_id, message=None):
        self.running.append((job_id, message))
        return None

    def complete_job(self, job_id, *, result=None, message=None):
        self.completed.append((job_id, result, message))
        return None

    def fail_job(self, job_id, message):
        self.failed.append((job_id, message))
        return None


class _FakeSystemIntegrityService:
    def __init__(self, session) -> None:
        del session
        self.run = DiagnosticRun(
            id=uuid4(),
            diagnostic_key="check_clip_embeddings",
            status="queued",
            related_job_id=uuid4(),
            latest_repair_job_id=uuid4(),
            repair_job_key="repair_clip_embeddings",
            created_at=datetime.now(timezone.utc),
        )
        self.stored_items: list[dict[str, object]] = []
        self.completed_calls: list[tuple[object, str]] = []
        self.failed_calls: list[str] = []

    def mark_run_started(self, run_id):
        self.run.id = run_id
        self.run.status = "running"
        return self.run

    def store_items(self, *, run_id, items):
        del run_id
        self.stored_items = list(items)

    def mark_run_completed(
        self,
        run_id,
        *,
        health_state,
        summary_json=None,
        sample_items_json=None,
    ):
        self.run.id = run_id
        self.run.status = "completed"
        self.run.health_state = health_state
        self.run.summary_json = summary_json
        self.run.sample_items_json = sample_items_json
        self.completed_calls.append((run_id, health_state))
        return self.run

    def mark_run_failed(self, run_id, *, error_message):
        self.run.id = run_id
        self.run.status = "failed"
        self.failed_calls.append(error_message)
        return self.run

    def get_run_model(self, run_id):
        self.run.id = run_id
        return self.run

    @property
    def repository(self):
        return self

    def list_run_items(self, *, diagnostic_run_id, limit=None, offset=0):
        del diagnostic_run_id, limit, offset
        return [
            types.SimpleNamespace(asset_id=uuid4(), person_id=None, relative_path=None)
        ]


class SystemIntegrityTasksTest(unittest.TestCase):
    def test_run_system_integrity_diagnostic_completes_related_job(self) -> None:
        fake_service = _FakeSystemIntegrityService(None)
        fake_job_service = _FakeJobService(None)

        with (
            patch(
                "app.services.system_integrity.tasks.Session",
                return_value=_SessionContext(),
            ),
            patch(
                "app.services.system_integrity.tasks.SystemIntegrityService",
                return_value=fake_service,
            ),
            patch(
                "app.services.system_integrity.tasks.JobService",
                return_value=fake_job_service,
            ),
            patch(
                "app.services.system_integrity.tasks._evaluate",
                return_value=types.SimpleNamespace(
                    health_state="warning",
                    summary={"affected_count": 2},
                    items=[
                        {"asset_id": uuid4(), "item_type": "asset", "reason_code": "x", "repairable": True}
                    ],
                ),
            ),
        ):
            asyncio.run(run_system_integrity_diagnostic({}, str(uuid4())))

        self.assertEqual(len(fake_service.stored_items), 1)
        self.assertEqual(len(fake_job_service.running), 1)
        self.assertEqual(len(fake_job_service.completed), 1)
        self.assertEqual(
            fake_job_service.completed[0][1]["health_state"],
            "warning",
        )

    def test_run_system_integrity_repair_completes_related_job(self) -> None:
        fake_service = _FakeSystemIntegrityService(None)
        fake_job_service = _FakeJobService(None)

        with (
            patch(
                "app.services.system_integrity.tasks.Session",
                return_value=_SessionContext(),
            ),
            patch(
                "app.services.system_integrity.tasks.SystemIntegrityService",
                return_value=fake_service,
            ),
            patch(
                "app.services.system_integrity.tasks.JobService",
                return_value=fake_job_service,
            ),
            patch(
                "app.services.system_integrity.tasks._repair_items",
                return_value={
                    "processed_count": 1,
                    "repaired_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                },
            ),
        ):
            asyncio.run(run_system_integrity_repair({}, str(uuid4())))

        self.assertEqual(len(fake_job_service.running), 1)
        self.assertEqual(len(fake_job_service.completed), 1)
        self.assertEqual(fake_job_service.completed[0][1]["repaired_count"], 1)


if __name__ == "__main__":
    unittest.main()
