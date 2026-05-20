from __future__ import annotations

import unittest
from uuid import uuid4

from app.models import AIModel
from app.services.ai_models.repository import AI_MODEL_TASK_FACE_RECOGNITION
from app.services.face_assignment.repository import (
    FaceAssignmentCandidate,
    FaceAssignmentNeighbor,
)
from app.services.face_assignment.service import FaceAssignmentService


class _FakeAIModelRepository:
    def __init__(self, model: AIModel) -> None:
        self.model = model

    def get_default_model_for_task(self, task: str) -> AIModel:
        if task != AI_MODEL_TASK_FACE_RECOGNITION:
            raise AssertionError(task)
        return self.model


class _FakeFaceAssignmentRepository:
    def __init__(
        self,
        *,
        asset_id,
        model_id: int,
        candidates: list[FaceAssignmentCandidate],
        neighbors: dict[tuple[str, int], list[FaceAssignmentNeighbor]],
    ) -> None:
        self.asset_id = asset_id
        self.model_id = model_id
        self.candidates = list(candidates)
        self.neighbors = neighbors
        self.assignment_calls: list[tuple[str, str]] = []
        self.last_model_ids: list[int] = []

    def list_assignment_candidates(self, *, asset_id, model_id):
        self.last_model_ids.append(model_id)
        if asset_id != self.asset_id:
            return []
        return list(self.candidates)

    def list_reference_neighbors(
        self,
        *,
        face_id,
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ):
        del distance_threshold, top_k
        self.last_model_ids.append(model_id)
        return list(self.neighbors.get((str(face_id), model_id), []))

    def assign_face_to_person(self, *, face_id, person_id):
        self.assignment_calls.append((str(face_id), str(person_id)))
        self.candidates = [
            candidate for candidate in self.candidates if candidate.id != face_id
        ]
        return True


class _FakeThumbnailService:
    def __init__(self) -> None:
        self.ensure_calls: list[str] = []

    def ensure_thumbnail(self, *, person_id):
        self.ensure_calls.append(str(person_id))


class FaceAssignmentServiceTest(unittest.TestCase):
    def _model(self, model_id: int = 17) -> AIModel:
        return AIModel(
            id=model_id,
            task=AI_MODEL_TASK_FACE_RECOGNITION,
            model_name="insightface-buffalo_l",
            version_tag="buffalo_l",
            vector_dimensions=512,
            is_deprecated=False,
        )

    def _candidate(self, *, asset_id, model_id: int) -> FaceAssignmentCandidate:
        return FaceAssignmentCandidate(
            id=uuid4(),
            asset_id=asset_id,
            face_model_id=model_id,
        )

    def test_confident_match_assigns_person_without_confirming(self) -> None:
        asset_id = uuid4()
        model = self._model()
        candidate = self._candidate(asset_id=asset_id, model_id=model.id)
        winning_person = uuid4()
        runner_up = uuid4()
        repo = _FakeFaceAssignmentRepository(
            asset_id=asset_id,
            model_id=model.id,
            candidates=[candidate],
            neighbors={
                (str(candidate.id), model.id): [
                    FaceAssignmentNeighbor(person_id=winning_person, distance=0.21),
                    FaceAssignmentNeighbor(person_id=winning_person, distance=0.24),
                    FaceAssignmentNeighbor(person_id=runner_up, distance=0.31),
                ]
            },
        )
        thumbnail_service = _FakeThumbnailService()
        service = FaceAssignmentService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=thumbnail_service,
        )

        result = service.assign_faces_for_asset(asset_id)

        self.assertEqual(result.faces_seen, 1)
        self.assertEqual(result.faces_matched, 1)
        self.assertEqual(result.faces_unmatched, 0)
        self.assertEqual(result.assignments[0].person_id, winning_person)
        self.assertEqual(result.assignments[0].distance, 0.21)
        self.assertEqual(
            repo.assignment_calls,
            [(str(candidate.id), str(winning_person))],
        )
        self.assertEqual(thumbnail_service.ensure_calls, [str(winning_person)])
        self.assertTrue(all(model_id == model.id for model_id in repo.last_model_ids))

    def test_insufficient_support_does_not_assign(self) -> None:
        asset_id = uuid4()
        model = self._model()
        candidate = self._candidate(asset_id=asset_id, model_id=model.id)
        repo = _FakeFaceAssignmentRepository(
            asset_id=asset_id,
            model_id=model.id,
            candidates=[candidate],
            neighbors={
                (str(candidate.id), model.id): [
                    FaceAssignmentNeighbor(person_id=uuid4(), distance=0.22),
                ]
            },
        )
        service = FaceAssignmentService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=_FakeThumbnailService(),
        )

        result = service.assign_faces_for_asset(asset_id)

        self.assertEqual(result.faces_matched, 0)
        self.assertEqual(result.faces_unmatched, 1)
        self.assertEqual(repo.assignment_calls, [])

    def test_ambiguous_margin_does_not_assign(self) -> None:
        asset_id = uuid4()
        model = self._model()
        candidate = self._candidate(asset_id=asset_id, model_id=model.id)
        person_a = uuid4()
        person_b = uuid4()
        repo = _FakeFaceAssignmentRepository(
            asset_id=asset_id,
            model_id=model.id,
            candidates=[candidate],
            neighbors={
                (str(candidate.id), model.id): [
                    FaceAssignmentNeighbor(person_id=person_a, distance=0.22),
                    FaceAssignmentNeighbor(person_id=person_a, distance=0.24),
                    FaceAssignmentNeighbor(person_id=person_b, distance=0.25),
                    FaceAssignmentNeighbor(person_id=person_b, distance=0.26),
                ]
            },
        )
        service = FaceAssignmentService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=_FakeThumbnailService(),
        )

        result = service.assign_faces_for_asset(asset_id, margin=0.05)

        self.assertEqual(result.faces_matched, 0)
        self.assertEqual(result.faces_unmatched, 1)
        self.assertEqual(repo.assignment_calls, [])

    def test_rerun_is_idempotent(self) -> None:
        asset_id = uuid4()
        model = self._model()
        candidate = self._candidate(asset_id=asset_id, model_id=model.id)
        person_id = uuid4()
        repo = _FakeFaceAssignmentRepository(
            asset_id=asset_id,
            model_id=model.id,
            candidates=[candidate],
            neighbors={
                (str(candidate.id), model.id): [
                    FaceAssignmentNeighbor(person_id=person_id, distance=0.18),
                    FaceAssignmentNeighbor(person_id=person_id, distance=0.21),
                ]
            },
        )
        thumbnail_service = _FakeThumbnailService()
        service = FaceAssignmentService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=thumbnail_service,
        )

        first = service.assign_faces_for_asset(asset_id)
        second = service.assign_faces_for_asset(asset_id)

        self.assertEqual(first.faces_matched, 1)
        self.assertEqual(second.faces_seen, 0)
        self.assertEqual(second.faces_matched, 0)
        self.assertEqual(len(thumbnail_service.ensure_calls), 1)


if __name__ == "__main__":
    unittest.main()
