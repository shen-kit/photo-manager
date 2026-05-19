from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.features.faces import (
    backfill_asset_faces,
    list_asset_faces,
    process_asset_faces,
    update_face,
)
from app.core.auth import get_current_user
from app.models import Face, Job, User
from app.services.faces.schemas import FaceUpdateRequest
from app.services.faces.service import FaceManagementServiceError


class _FakeJobService:
    def __init__(self, job: Job | None = None) -> None:
        self.job = job
        self.failed: list[tuple[object, str]] = []
        self.created: list[tuple[str, dict[str, object] | None, int | None]] = []

    def get_job(self, job_id):
        if self.job is None:
            raise AssertionError(job_id)
        return self.job

    def fail_job(self, job_id, message):
        self.failed.append((job_id, message))

    def create_job(self, type: str, parameters=None, progress_total=None):
        self.created.append((type, parameters, progress_total))
        if self.job is None:
            self.job = Job(
                id=uuid4(),
                type=type,
                status="queued",
                progress_current=0,
                progress_total=progress_total,
                parameters=parameters,
                created_at=datetime.now(timezone.utc),
            )
        return self.job


class _FakeFaceQueryService:
    def __init__(self, *, exists: bool = True, faces: list[Face] | None = None) -> None:
        self.exists = exists
        self.faces = faces or []
        self.required_asset_ids = []
        self.session = object()

    def require_active_asset(self, asset_id):
        self.required_asset_ids.append(asset_id)
        if not self.exists:
            raise HTTPException(status_code=404, detail="Asset not found")
        return SimpleNamespace(id=asset_id)

    def list_faces_for_asset(self, asset_id):
        self.require_active_asset(asset_id)
        return list(self.faces)


class FacesApiTest(unittest.TestCase):
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

    def test_backfill_endpoint_enqueues_job(self) -> None:
        job = Job(
            id=uuid4(),
            type="generate_missing_asset_faces",
            status="queued",
            progress_current=0,
            progress_total=4,
            created_at=datetime.now(timezone.utc),
        )
        job_service = _FakeJobService(job)

        with (
            patch(
                "app.api.v1.features.faces.create_backfill_job",
                return_value=(job.id, 4),
            ),
            patch(
                "app.api.v1.features.faces.enqueue_missing_asset_faces_job",
                new=AsyncMock(return_value=True),
            ) as enqueue_mock,
        ):
            response = asyncio.run(
                backfill_asset_faces(
                    force=True,
                    job_service=job_service,
                    current_user=self.user,
                )
            )

        self.assertEqual(response.id, job.id)
        enqueue_mock.assert_awaited_once_with(job.id, force=True)

    def test_process_asset_endpoint_enqueues_specific_asset(self) -> None:
        asset_id = uuid4()
        job = Job(
            id=uuid4(),
            type="process_asset_faces",
            status="queued",
            progress_current=0,
            created_at=datetime.now(timezone.utc),
        )
        job_service = _FakeJobService(job)
        face_query_service = _FakeFaceQueryService()

        with patch(
            "app.api.v1.features.faces.enqueue_asset_faces_job",
            new=AsyncMock(return_value=True),
        ) as enqueue_mock:
            response = asyncio.run(
                process_asset_faces(
                    asset_id=asset_id,
                    force=True,
                    face_query_service=face_query_service,
                    job_service=job_service,
                    current_user=self.user,
                )
            )

        self.assertEqual(response.id, job.id)
        self.assertEqual(job_service.created[0][0], "process_asset_faces")
        self.assertEqual(
            job_service.created[0][1],
            {"asset_id": str(asset_id), "force": True},
        )
        enqueue_mock.assert_awaited_once_with(asset_id, force=True, job_id=job.id)

    def test_get_faces_hides_embeddings(self) -> None:
        asset_id = uuid4()
        face = Face(
            id=uuid4(),
            asset_id=asset_id,
            person_id=None,
            bounding_box={
                "x": 1,
                "y": 2,
                "width": 30,
                "height": 40,
                "image_width": 300,
                "image_height": 200,
            },
            embedding=[0.1] * 512,
            confidence=0.98,
            crop_path="assets/crops/example.webp",
            is_confirmed=False,
            is_excluded=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        face_query_service = _FakeFaceQueryService(faces=[face])

        response = list_asset_faces(
            asset_id=asset_id,
            request=self.request,
            face_query_service=face_query_service,
            current_user=self.user,
        )

        payload = response[0].model_dump()
        self.assertNotIn("embedding", payload)
        self.assertEqual(payload["detection_confidence"], 0.98)
        self.assertEqual(
            payload["crop_url"],
            "http://testserver/media/processed/assets/crops/example.webp",
        )

    def test_missing_asset_returns_404(self) -> None:
        face_query_service = _FakeFaceQueryService(exists=False)
        asset_id = uuid4()

        with self.assertRaises(HTTPException) as get_exc:
            list_asset_faces(
                asset_id=asset_id,
                request=self.request,
                face_query_service=face_query_service,
                current_user=self.user,
            )
        with self.assertRaises(HTTPException) as process_exc:
            asyncio.run(
                process_asset_faces(
                    asset_id=asset_id,
                    force=False,
                    face_query_service=face_query_service,
                    job_service=_FakeJobService(),
                    current_user=self.user,
                )
            )

        self.assertEqual(get_exc.exception.status_code, 404)
        self.assertEqual(process_exc.exception.status_code, 404)

    def test_update_face_endpoint_hides_embeddings_and_returns_updated_face(self) -> None:
        face = Face(
            id=uuid4(),
            asset_id=uuid4(),
            person_id=uuid4(),
            bounding_box={
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "image_width": 300,
                "image_height": 200,
            },
            embedding=[0.1] * 512,
            confidence=0.95,
            crop_path=None,
            is_confirmed=True,
            is_excluded=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch(
            "app.api.v1.features.faces.FaceManagementService.update_face",
            return_value=face,
        ) as update_mock:
            response = update_face(
                face_id=face.id,
                payload=FaceUpdateRequest(person_id=face.person_id),
                request=self.request,
                face_query_service=_FakeFaceQueryService(),
                current_user=self.user,
            )

        update_mock.assert_called_once()
        payload = response.model_dump()
        self.assertNotIn("embedding", payload)
        self.assertTrue(payload["is_confirmed"])

    def test_update_face_endpoint_returns_400_for_invalid_assignment(self) -> None:
        with patch(
            "app.api.v1.features.faces.FaceManagementService.update_face",
            side_effect=FaceManagementServiceError(
                "Excluded face cannot be assigned without explicitly unexcluding it"
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                update_face(
                    face_id=uuid4(),
                    payload=FaceUpdateRequest(person_id=uuid4()),
                    request=self.request,
                    face_query_service=_FakeFaceQueryService(),
                    current_user=self.user,
                )

        self.assertEqual(exc.exception.status_code, 400)

    def test_authentication_helper_rejects_missing_credentials(self) -> None:
        with self.assertRaises(HTTPException) as exc:
            get_current_user(credentials=None, session=SimpleNamespace())

        self.assertEqual(exc.exception.status_code, 401)
        self.assertEqual(exc.exception.detail, "Authentication required")


if __name__ == "__main__":
    unittest.main()
