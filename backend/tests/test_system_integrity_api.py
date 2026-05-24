from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException

from app.api.v1.features.system_integrity import (
    get_latest_diagnostic_run,
    list_diagnostics,
    list_run_items,
    repair_run,
    run_diagnostic,
)
from app.models import DiagnosticRun, Job, User
from app.services.system_integrity.schemas import (
    DiagnosticDefinitionListRead,
    DiagnosticRunItemPageRead,
    DiagnosticRunRead,
)


class _FakeSystemIntegrityService:
    def __init__(self) -> None:
        self.user_run_requests: list[str] = []
        self.created_run = DiagnosticRun(
            id=uuid4(),
            diagnostic_key="check_clip_embeddings",
            status="queued",
            repair_job_key="repair_clip_embeddings",
            created_at=datetime.now(timezone.utc),
        )
        self.run_model = DiagnosticRun(
            id=uuid4(),
            diagnostic_key="check_people_without_active_faces",
            status="completed",
            repair_job_key="repair_people_without_active_faces",
            created_at=datetime.now(timezone.utc),
        )

    def list_definitions(self):
        return DiagnosticDefinitionListRead(items=[])

    def create_run(self, *, diagnostic_key, requested_by_user_id=None):
        del requested_by_user_id
        self.user_run_requests.append(diagnostic_key)
        self.created_run.diagnostic_key = diagnostic_key
        return self.created_run

    def attach_related_job(self, *, run_id, related_job_id):
        self.created_run.related_job_id = related_job_id
        return self.created_run

    def get_run_read(self, run):
        return DiagnosticRunRead.model_validate(run, from_attributes=True)

    def get_latest_run(self, *, diagnostic_key):
        self.created_run.diagnostic_key = diagnostic_key
        return DiagnosticRunRead.model_validate(self.created_run, from_attributes=True)

    def list_run_items(self, *, run_id, limit=100, offset=0):
        del run_id, limit, offset
        return DiagnosticRunItemPageRead(items=[], limit=100, offset=0, total=0)

    def get_run_model(self, run_id):
        del run_id
        return self.run_model

    def attach_latest_repair_job(self, *, run_id, latest_repair_job_id):
        del run_id
        self.run_model.latest_repair_job_id = latest_repair_job_id
        return self.run_model


class SystemIntegrityApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user = User(
            id=uuid4(),
            username="tester",
            password_hash="x",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_list_diagnostics_returns_service_payload(self) -> None:
        service = _FakeSystemIntegrityService()

        response = list_diagnostics(service=service, current_user=self.user)

        self.assertEqual(response.items, [])

    def test_run_diagnostic_dispatches_job(self) -> None:
        service = _FakeSystemIntegrityService()
        dispatch_job = Job(
            id=uuid4(),
            type="run_system_integrity_diagnostic",
            status="queued",
            progress_current=0,
            is_visible=True,
            created_at=datetime.now(timezone.utc),
        )

        async def _fake_dispatch(**kwargs):
            del kwargs
            return type("DispatchResult", (), {"job": dispatch_job})()

        with patch(
            "app.api.v1.features.system_integrity.dispatch_with_new_session",
            _fake_dispatch,
        ):
            response = asyncio.run(
                run_diagnostic(
                    diagnostic_key="check_clip_embeddings",
                    service=service,
                    current_user=self.user,
                )
            )

        self.assertEqual(service.user_run_requests, ["check_clip_embeddings"])
        self.assertEqual(response.run.related_job_id, dispatch_job.id)

    def test_get_latest_run_delegates(self) -> None:
        service = _FakeSystemIntegrityService()

        response = get_latest_diagnostic_run(
            diagnostic_key="check_clip_embeddings",
            service=service,
            current_user=self.user,
        )

        self.assertEqual(response.run.diagnostic_key, "check_clip_embeddings")

    def test_repair_run_blocks_detect_only_diagnostic(self) -> None:
        service = _FakeSystemIntegrityService()
        service.run_model.repair_job_key = None

        with self.assertRaises(HTTPException) as exc:
            asyncio.run(
                repair_run(
                    run_id=service.run_model.id,
                    service=service,
                    current_user=self.user,
                )
            )

        self.assertEqual(exc.exception.status_code, 400)

    def test_list_run_items_returns_page(self) -> None:
        service = _FakeSystemIntegrityService()

        response = list_run_items(
            run_id=service.run_model.id,
            service=service,
            current_user=self.user,
        )

        self.assertEqual(response.total, 0)


if __name__ == "__main__":
    unittest.main()
