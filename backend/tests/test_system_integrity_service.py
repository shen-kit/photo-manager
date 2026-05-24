from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models import DiagnosticRun, DiagnosticRunItem
from app.services.system_integrity.service import SystemIntegrityService


class _FakeRepository:
    def __init__(self) -> None:
        self.active_by_key: dict[str, DiagnosticRun | None] = {}
        self.latest_by_key: dict[str, DiagnosticRun | None] = {}
        self.runs_by_id: dict[object, DiagnosticRun] = {}
        self.run_items_by_run_id: dict[object, list[DiagnosticRunItem]] = {}
        self.deleted_runs: list[DiagnosticRun] = []

    def get_latest_run(self, *, diagnostic_key: str):
        return self.latest_by_key.get(diagnostic_key)

    def get_active_run(self, *, diagnostic_key: str):
        return self.active_by_key.get(diagnostic_key)

    def create_run(self, **kwargs):
        run = DiagnosticRun(
            id=uuid4(),
            diagnostic_key=kwargs["diagnostic_key"],
            status=kwargs["status"],
            repair_job_key=kwargs.get("repair_job_key"),
            requested_by_user_id=kwargs.get("requested_by_user_id"),
            created_at=datetime.now(timezone.utc),
        )
        self.runs_by_id[run.id] = run
        return run

    def get_run(self, run_id):
        run = self.runs_by_id.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def save_run(self, run):
        self.runs_by_id[run.id] = run
        return run

    def list_runs(self, *, diagnostic_key=None, limit=50, offset=0):
        runs = list(self.runs_by_id.values())
        if diagnostic_key is not None:
            runs = [run for run in runs if run.diagnostic_key == diagnostic_key]
        return runs[offset : offset + limit]

    def list_run_items(self, *, diagnostic_run_id, limit=100, offset=0):
        items = list(self.run_items_by_run_id.get(diagnostic_run_id, []))
        if limit is None:
            return items[offset:]
        return items[offset : offset + limit]

    def count_run_items(self, *, diagnostic_run_id):
        return len(self.run_items_by_run_id.get(diagnostic_run_id, []))

    def list_runs_for_retention(self, *, diagnostic_key):
        return [
            run
            for run in sorted(
                self.runs_by_id.values(),
                key=lambda run: (run.created_at, run.id),
                reverse=True,
            )
            if run.diagnostic_key == diagnostic_key
        ]

    def delete_runs(self, runs):
        self.deleted_runs.extend(runs)


class SystemIntegrityServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = _FakeRepository()
        self.service = SystemIntegrityService(session=None, repository=self.repository)

    def test_create_run_blocks_active_duplicate(self) -> None:
        active_run = DiagnosticRun(
            id=uuid4(),
            diagnostic_key="check_clip_embeddings",
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        self.repository.active_by_key["check_clip_embeddings"] = active_run

        with self.assertRaises(HTTPException) as exc:
            self.service.create_run(diagnostic_key="check_clip_embeddings")

        self.assertEqual(exc.exception.status_code, 409)

    def test_list_run_items_returns_paginated_page(self) -> None:
        run_id = uuid4()
        run = DiagnosticRun(
            id=run_id,
            diagnostic_key="check_clip_embeddings",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        self.repository.runs_by_id[run_id] = run
        self.repository.run_items_by_run_id[run_id] = [
            DiagnosticRunItem(
                id=uuid4(),
                diagnostic_run_id=run_id,
                item_type="asset",
                reason_code="one",
                repairable=True,
                created_at=datetime.now(timezone.utc),
            ),
            DiagnosticRunItem(
                id=uuid4(),
                diagnostic_run_id=run_id,
                item_type="asset",
                reason_code="two",
                repairable=True,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        page = self.service.list_run_items(run_id=run_id, limit=1, offset=1)

        self.assertEqual(page.total, 2)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].reason_code, "two")

    def test_mark_run_completed_applies_retention(self) -> None:
        diagnostic_key = "check_face_processing"
        runs = []
        for index in range(4):
            run = DiagnosticRun(
                id=uuid4(),
                diagnostic_key=diagnostic_key,
                status="queued",
                created_at=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
            )
            self.repository.runs_by_id[run.id] = run
            runs.append(run)

        self.service.mark_run_completed(
            runs[0].id,
            health_state="healthy",
            summary_json={"affected_count": 0},
        )

        self.assertEqual(len(self.repository.deleted_runs), 1)
        self.assertEqual(self.repository.deleted_runs[0].id, runs[0].id)


if __name__ == "__main__":
    unittest.main()
