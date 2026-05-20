from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4
from unittest.mock import patch

from app.services.faces.service import FaceProcessingResult
from app.services.faces.tasks import process_asset_faces


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeJobService:
    def __init__(self, session) -> None:
        del session
        self.completed: list[dict[str, object]] = []

    def mark_running(self, job_id, message):
        del job_id, message

    def complete_job(self, job_id, *, result, message):
        self.completed.append({"job_id": job_id, "result": result, "message": message})


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

        with (
            patch("app.services.faces.tasks.Session", return_value=_FakeSession()),
            patch("app.services.faces.tasks.JobService", _FakeJobService),
            patch(
                "app.services.faces.tasks.FaceProcessingService.process_asset_faces",
                return_value=processing_result,
            ),
            patch(
                "app.services.faces.tasks.FaceAssignmentService.assign_faces_for_asset",
                return_value=assignment_result,
            ) as assign_mock,
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

        assign_mock.assert_called_once_with(asset_id)

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

        with (
            patch("app.services.faces.tasks.Session", return_value=_FakeSession()),
            patch("app.services.faces.tasks.JobService", _FakeJobService),
            patch(
                "app.services.faces.tasks.FaceProcessingService.process_asset_faces",
                return_value=processing_result,
            ),
            patch(
                "app.services.faces.tasks.FaceAssignmentService.assign_faces_for_asset",
            ) as assign_mock,
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

        assign_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
