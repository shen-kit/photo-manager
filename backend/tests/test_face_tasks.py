from __future__ import annotations

import asyncio
import sys
import unittest
from uuid import uuid4
from unittest.mock import MagicMock, patch

sys.modules.setdefault("open_clip", MagicMock())
sys.modules.setdefault("torch", MagicMock())

from app.services.faces.service import FaceProcessingResult
from app.services.faces.tasks import process_asset_faces


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeJobTaskContext:
    def __init__(self, session, *, job_id) -> None:
        del session
        self.job_id = job_id
        self.running_messages: list[str] = []
        self.completed: list[dict[str, object]] = []

    def mark_running(self, message):
        self.running_messages.append(message)

    def complete(self, message, *, result=None, notification=None):
        del notification
        self.completed.append(
            {"job_id": self.job_id, "result": result, "message": message}
        )


class _FakeTracker:
    def __init__(self, session) -> None:
        del session
        self.running_calls: list[dict[str, object]] = []
        self.completed_calls: list[dict[str, object]] = []

    def mark_running(self, **kwargs):
        self.running_calls.append(kwargs)

    def mark_completed(self, **kwargs):
        self.completed_calls.append(kwargs)


class _FakeAIModelRepository:
    def get_default_model_for_task(self, task: str):
        del task
        return type("FaceModel", (), {"id": 17})()


class _FakeFaceProcessingService:
    def __init__(self, session, result: FaceProcessingResult) -> None:
        del session
        self.ai_model_repository = _FakeAIModelRepository()
        self._result = result

    def process_asset_faces(self, asset_id, *, force=False):
        del asset_id, force
        return self._result


class _FakeFaceAssignmentService:
    def __init__(self, session, assignment_result) -> None:
        del session
        self.assignment_result = assignment_result
        self.calls: list[object] = []

    def assign_faces_for_asset(self, asset_id):
        self.calls.append(asset_id)
        return self.assignment_result


class FaceTasksTest(unittest.TestCase):
    def test_process_asset_faces_runs_incremental_assignment_when_enabled(self) -> None:
        asset_id = uuid4()
        job_id = uuid4()
        processing_result = FaceProcessingResult(
            asset_id=asset_id,
            model_id=17,
            processed=True,
            skipped=False,
            faces_created=2,
            detected_faces=2,
            deleted_unconfirmed_faces=0,
        )
        assignment_result = type(
            "AssignmentResult",
            (),
            {
                "faces_seen": 2,
                "faces_matched": 1,
                "faces_unmatched": 1,
            },
        )()
        job_contexts: list[_FakeJobTaskContext] = []
        trackers: list[_FakeTracker] = []
        assignment_services: list[_FakeFaceAssignmentService] = []

        def make_job_context(session, *, job_id):
            context = _FakeJobTaskContext(session, job_id=job_id)
            job_contexts.append(context)
            return context

        def make_tracker(session):
            tracker = _FakeTracker(session)
            trackers.append(tracker)
            return tracker

        def make_face_service(session):
            return _FakeFaceProcessingService(session, processing_result)

        def make_assignment_service(session):
            service = _FakeFaceAssignmentService(session, assignment_result)
            assignment_services.append(service)
            return service

        with (
            patch("app.services.faces.tasks.Session", return_value=_FakeSession()),
            patch(
                "app.services.faces.tasks.JobTaskContext",
                side_effect=make_job_context,
            ),
            patch(
                "app.services.faces.tasks.AssetProcessingTrackerService",
                side_effect=make_tracker,
            ),
            patch(
                "app.services.faces.tasks.FaceProcessingService",
                side_effect=make_face_service,
            ),
            patch(
                "app.services.faces.tasks.FaceAssignmentService",
                side_effect=make_assignment_service,
            ),
        ):
            asyncio.run(
                process_asset_faces(
                    {},
                    str(asset_id),
                    False,
                    True,
                    str(job_id),
                )
            )

        self.assertEqual(len(job_contexts), 1)
        self.assertEqual(job_contexts[0].running_messages, ["Processing asset faces"])
        self.assertEqual(
            job_contexts[0].completed[0]["result"]["faces_matched"],
            assignment_result.faces_matched,
        )
        self.assertEqual(len(trackers), 1)
        self.assertEqual(trackers[0].running_calls[0]["asset_id"], asset_id)
        self.assertEqual(trackers[0].completed_calls[0]["asset_id"], asset_id)
        self.assertEqual(len(assignment_services), 1)
        self.assertEqual(assignment_services[0].calls, [asset_id])

    def test_process_asset_faces_skips_incremental_assignment_when_disabled(
        self,
    ) -> None:
        asset_id = uuid4()
        job_id = uuid4()
        processing_result = FaceProcessingResult(
            asset_id=asset_id,
            model_id=17,
            processed=True,
            skipped=False,
            faces_created=1,
            detected_faces=1,
            deleted_unconfirmed_faces=0,
        )
        assignment_services: list[_FakeFaceAssignmentService] = []

        def make_face_service(session):
            return _FakeFaceProcessingService(session, processing_result)

        def make_assignment_service(session):
            service = _FakeFaceAssignmentService(session, assignment_result=None)
            assignment_services.append(service)
            return service

        with (
            patch("app.services.faces.tasks.Session", return_value=_FakeSession()),
            patch(
                "app.services.faces.tasks.JobTaskContext",
                side_effect=_FakeJobTaskContext,
            ),
            patch(
                "app.services.faces.tasks.AssetProcessingTrackerService",
                side_effect=_FakeTracker,
            ),
            patch(
                "app.services.faces.tasks.FaceProcessingService",
                side_effect=make_face_service,
            ),
            patch(
                "app.services.faces.tasks.FaceAssignmentService",
                side_effect=make_assignment_service,
            ),
        ):
            asyncio.run(
                process_asset_faces(
                    {},
                    str(asset_id),
                    False,
                    False,
                    str(job_id),
                )
            )

        self.assertEqual(assignment_services, [])


if __name__ == "__main__":
    unittest.main()
