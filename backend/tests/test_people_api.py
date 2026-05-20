from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.features.people import (
    get_person,
    merge_people,
)
from app.models import Job, Person, User
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
        self.request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("testserver", 80),
                "headers": [],
            }
        )

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

    def test_get_person_adds_face_id_cache_buster_to_thumbnail_url(self) -> None:
        person_id = uuid4()
        thumbnail_face_id = uuid4()
        person = Person(
            id=person_id,
            name="Alice",
            thumbnail_face_id=thumbnail_face_id,
            thumbnail_path="generated/people/thumbnails/example.webp",
            thumbnail_manually_set=True,
            is_hidden=False,
        )

        class _PersonDetail:
            def __init__(self, person):
                self.person = person
                self.face_count = 3
                self.asset_count = 2
                self.thumbnail_path = person.thumbnail_path

        class _PeopleService:
            def get_person_detail(self, requested_person_id):
                self.requested_person_id = requested_person_id
                return _PersonDetail(person)

        people_service = _PeopleService()

        response = get_person(
            person_id=person_id,
            request=self.request,
            people_service=people_service,
            current_user=self.user,
        )

        self.assertEqual(people_service.requested_person_id, person_id)
        self.assertEqual(
            response.thumbnail_url,
            f"http://testserver/media/processed/generated/people/thumbnails/example.webp?face_id={thumbnail_face_id}",
        )


if __name__ == "__main__":
    unittest.main()
