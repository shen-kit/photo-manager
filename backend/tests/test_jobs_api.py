from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.api.v1.features.jobs import (
    get_job,
    list_available_jobs,
    list_jobs,
    run_manual_job,
)
from app.models import Job, User
from app.services.jobs.schemas import JobDetailRead
from app.services.manual_jobs.schemas import (
    ManualJobCatalogRead,
    ManualJobDefinitionRead,
    ManualJobParameterRead,
    ManualJobRunRequest,
)


class _FakeManualJobService:
    def __init__(self) -> None:
        self.run_calls: list[tuple[str, dict[str, object] | None]] = []
        self.catalog = ManualJobCatalogRead(
            items=[
                ManualJobDefinitionRead(
                    job_key="run_missing_or_outdated_face_recognition",
                    title="Run Face Recognition",
                    description="Test",
                    category="face",
                    mode="batched",
                    supports_dry_run=False,
                    batch_size=50,
                    pending_count=3,
                    parameters=[
                        ManualJobParameterRead(
                            name="force",
                            type="boolean",
                            default=False,
                        ),
                        ManualJobParameterRead(
                            name="auto_match",
                            type="boolean",
                            default=False,
                        ),
                    ],
                    default_params={"force": False, "auto_match": False},
                )
            ]
        )
        self.job = Job(
            id=uuid4(),
            type="manual_job:run_missing_or_outdated_face_recognition",
            job_key="run_missing_or_outdated_face_recognition",
            status="queued",
            progress_current=0,
            progress_total=3,
            parameters={},
            parent_job_id=None,
            related_asset_id=None,
            is_visible=True,
            created_at=datetime.now(timezone.utc),
        )
        self.job_detail = None

    def list_available_jobs(self):
        return self.catalog

    async def run_manual_job(self, *, job_key, request, requested_by_user_id=None):
        del requested_by_user_id
        self.run_calls.append(
            (job_key, request.params if request else None)
        )
        return self.job

    def build_job_detail(self, job_id, *, include_children):
        del include_children
        if self.job_detail is not None:
            return self.job_detail
        raise AssertionError(job_id)


class _FakeJobService:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def list_jobs(
        self,
        *,
        status=None,
        type=None,
        limit=50,
        offset=0,
        include_children=False,
        parent_job_id=None,
    ):
        del status, type, limit, offset, include_children, parent_job_id
        return list(self.jobs)


class JobsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user = User(
            id=uuid4(),
            username="tester",
            password_hash="x",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_list_available_jobs_returns_catalog(self) -> None:
        service = _FakeManualJobService()

        response = list_available_jobs(
            manual_job_service=service,
            current_user=self.user,
        )

        self.assertEqual(len(response.items), 1)
        self.assertEqual(
            response.items[0].job_key, "run_missing_or_outdated_face_recognition"
        )

    def test_run_manual_job_returns_created_job(self) -> None:
        service = _FakeManualJobService()

        response = asyncio.run(
            run_manual_job(
                job_key="run_missing_or_outdated_face_recognition",
                payload=None,
                manual_job_service=service,
                current_user=self.user,
            )
        )

        self.assertEqual(
            service.run_calls, [("run_missing_or_outdated_face_recognition", None)]
        )
        self.assertEqual(response.job.id, service.job.id)
        self.assertEqual(response.job.job_key, service.job.job_key)

    def test_run_manual_job_passes_params(self) -> None:
        service = _FakeManualJobService()

        response = asyncio.run(
            run_manual_job(
                job_key="run_missing_or_outdated_face_recognition",
                payload=ManualJobRunRequest(
                    params={"force": True, "auto_match": True}
                ),
                manual_job_service=service,
                current_user=self.user,
            )
        )

        self.assertEqual(
            service.run_calls,
            [
                (
                    "run_missing_or_outdated_face_recognition",
                    {"force": True, "auto_match": True},
                )
            ],
        )
        self.assertEqual(response.job.id, service.job.id)

    def test_run_manual_job_conflict_bubbles_up(self) -> None:
        service = _FakeManualJobService()

        async def _raise_conflict(*, job_key, request, requested_by_user_id=None):
            del request, requested_by_user_id
            raise HTTPException(
                status_code=409,
                detail={
                    "detail": "Manual job already active",
                    "job_key": job_key,
                    "active_job_id": str(uuid4()),
                },
            )

        service.run_manual_job = _raise_conflict

        with self.assertRaises(HTTPException) as exc:
            asyncio.run(
                run_manual_job(
                    job_key="run_missing_or_outdated_face_recognition",
                    payload=None,
                    manual_job_service=service,
                    current_user=self.user,
                )
            )

        self.assertEqual(exc.exception.status_code, 409)
        self.assertIn("active_job_id", exc.exception.detail)

    def test_list_jobs_uses_existing_job_service_filters(self) -> None:
        job = Job(
            id=uuid4(),
            type="manual_job:bulk_scan",
            job_key="bulk_scan",
            status="completed",
            progress_current=0,
            progress_total=0,
            parameters=None,
            parent_job_id=None,
            related_asset_id=None,
            is_visible=True,
            created_at=datetime.now(timezone.utc),
        )

        response = list_jobs(
            job_service=_FakeJobService([job]),
            current_user=self.user,
        )

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].job_key, "bulk_scan")

    def test_get_job_returns_detail_shape(self) -> None:
        service = _FakeManualJobService()
        service.job_detail = JobDetailRead.model_validate(
            {
                "id": str(service.job.id),
                "type": service.job.type,
                "job_key": service.job.job_key,
                "status": service.job.status,
                "progress_current": 0,
                "progress_total": 3,
                "progress_message": None,
                "parameters": {},
                "result": None,
                "error_message": None,
                "parent_job_id": None,
                "related_asset_id": None,
                "is_visible": True,
                "created_at": service.job.created_at,
                "started_at": None,
                "finished_at": None,
                "child_counts": {
                    "total": 0,
                    "queued": 0,
                    "running": 0,
                    "completed": 0,
                    "failed": 0,
                    "cancelled": 0,
                },
                "children": [],
            }
        )

        response = get_job(
            job_id=service.job.id,
            include_children=True,
            manual_job_service=service,
            current_user=self.user,
        )

        self.assertEqual(response.id, service.job.id)
        self.assertEqual(response.job_key, service.job.job_key)


if __name__ == "__main__":
    unittest.main()
