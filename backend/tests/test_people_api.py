from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.features.people import (
    PeopleClusteringRequest,
    cluster_people,
    merge_people,
)
from app.models import Job, User
from app.services.people.service import PersonMergeSummary
from app.services.people_clustering.tasks import cluster_faces


class _FakeJobService:
    def __init__(self, job: Job | None = None) -> None:
        self.job = job
        self.failed: list[tuple[object, str]] = []

    def get_job(self, job_id):
        if self.job is None:
            raise AssertionError(job_id)
        return self.job

    def fail_job(self, job_id, message):
        self.failed.append((job_id, message))

    def mark_running(self, job_id, message=None):
        return self.job

    def complete_job(self, job_id, *, result=None, message=None):
        return self.job


class PeopleApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.user = User(
            id=uuid4(),
            username="tester",
            password_hash="x",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_cluster_endpoint_enqueues_job(self) -> None:
        job = Job(
            id=uuid4(),
            type="cluster_faces",
            status="queued",
            progress_current=0,
            created_at=datetime.now(timezone.utc),
        )
        job_service = _FakeJobService(job)
        payload = PeopleClusteringRequest(threshold=0.35, top_k=25, min_cluster_size=3)

        with (
            patch(
                "app.api.v1.features.people.create_clustering_job",
                return_value=job.id,
            ),
            patch(
                "app.api.v1.features.people.enqueue_face_clustering_job",
                new=AsyncMock(return_value=True),
            ) as enqueue_mock,
        ):
            response = asyncio.run(
                cluster_people(
                    payload=payload,
                    job_service=job_service,
                    current_user=self.user,
                )
            )

        self.assertEqual(response.id, job.id)
        enqueue_mock.assert_awaited_once_with(
            job.id,
            threshold=0.35,
            top_k=25,
            min_cluster_size=3,
        )

    def test_invalid_params_are_rejected(self) -> None:
        job_service = _FakeJobService()

        with self.assertRaises(HTTPException) as threshold_exc:
            asyncio.run(
                cluster_people(
                    payload=PeopleClusteringRequest(
                        threshold=0.1,
                        top_k=25,
                        min_cluster_size=3,
                    ),
                    job_service=job_service,
                    current_user=self.user,
                )
            )
        with self.assertRaises(HTTPException) as top_k_exc:
            asyncio.run(
                cluster_people(
                    payload=PeopleClusteringRequest(
                        threshold=0.4,
                        top_k=3,
                        min_cluster_size=3,
                    ),
                    job_service=job_service,
                    current_user=self.user,
                )
            )
        with self.assertRaises(HTTPException) as min_cluster_size_exc:
            asyncio.run(
                cluster_people(
                    payload=PeopleClusteringRequest(
                        threshold=0.4,
                        top_k=25,
                        min_cluster_size=1,
                    ),
                    job_service=job_service,
                    current_user=self.user,
                )
            )

        self.assertEqual(threshold_exc.exception.status_code, 422)
        self.assertEqual(top_k_exc.exception.status_code, 422)
        self.assertEqual(min_cluster_size_exc.exception.status_code, 422)

    def test_worker_task_calls_clustering_service(self) -> None:
        class _Summary:
            candidates_seen = 4
            clusters_created = 1
            faces_assigned = 3
            skipped_small_clusters = 1

        class _Service:
            def __init__(self, session):
                self.session = session

            def cluster_unassigned_faces(self, **kwargs):
                self.kwargs = kwargs
                return _Summary()

        job = Job(
            id=uuid4(),
            type="cluster_faces",
            status="queued",
            progress_current=0,
            created_at=datetime.now(timezone.utc),
        )

        class _NotificationService:
            def __init__(self, session):
                self.session = session

            def create_notification(self, **kwargs):
                return None

        class _SessionContext:
            def __enter__(self):
                return object()

            def __exit__(self, exc_type, exc, tb):
                return False

        job_service = _FakeJobService(job)

        with (
            patch(
                "app.services.people_clustering.tasks.Session",
                return_value=_SessionContext(),
            ),
            patch(
                "app.services.people_clustering.tasks.JobService",
                return_value=job_service,
            ),
            patch(
                "app.services.people_clustering.tasks.NotificationService",
                _NotificationService,
            ),
            patch(
                "app.services.people_clustering.tasks.PeopleClusteringService",
                _Service,
            ),
        ):
            result = asyncio.run(
                cluster_faces(
                    {},
                    str(job.id),
                    0.4,
                    30,
                    2,
                )
            )

        self.assertEqual(
            result,
            {
                "candidates_seen": 4,
                "clusters_created": 1,
                "faces_assigned": 3,
                "skipped_small_clusters": 1,
            },
        )

    def test_merge_people_endpoint_returns_summary(self) -> None:
        source_person_id = uuid4()
        target_person_id = uuid4()

        class _PeopleService:
            def merge_people(self, *, source_person_id, target_person_id):
                return PersonMergeSummary(
                    faces_moved=5,
                    source_deleted=True,
                    target_person_id=target_person_id,
                )

        response = merge_people(
            source_person_id=source_person_id,
            target_person_id=target_person_id,
            people_service=_PeopleService(),
            current_user=self.user,
        )

        self.assertEqual(response.faces_moved, 5)
        self.assertTrue(response.source_deleted)
        self.assertEqual(response.target_person_id, target_person_id)


if __name__ == "__main__":
    unittest.main()
