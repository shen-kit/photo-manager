from __future__ import annotations

import unittest
from uuid import uuid4

from app.models import AIModel
from app.services.ai_models.repository import AI_MODEL_TASK_FACE_RECOGNITION
from app.services.people_clustering.repository import FaceClusterCandidate
from app.services.people_clustering.service import (
    PeopleClusteringService,
)


class _FakeAIModelRepository:
    def __init__(self, model: AIModel) -> None:
        self.model = model

    def get_default_model_for_task(self, task: str) -> AIModel:
        if task != AI_MODEL_TASK_FACE_RECOGNITION:
            raise AssertionError(task)
        return self.model


class _FakePeopleClusteringRepository:
    def __init__(
        self,
        *,
        candidates: list[FaceClusterCandidate],
        neighbors: dict[tuple[str, int], list[str]],
    ) -> None:
        self.candidates_by_id = {candidate.id: candidate for candidate in candidates}
        self.neighbors = neighbors
        self.created_people: list[object] = []
        self.assignments: dict[str, list[str]] = {}
        self.last_model_ids: list[int] = []

    def list_cluster_candidates(self, *, model_id: int) -> list[FaceClusterCandidate]:
        self.last_model_ids.append(model_id)
        return list(self.candidates_by_id.values())

    def list_neighbor_face_ids(
        self,
        *,
        face_id,
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> list:
        self.last_model_ids.append(model_id)
        values = self.neighbors.get((str(face_id), model_id), [])
        return [self._uuid(value) for value in values[:top_k]]

    def create_person(self):
        person_id = uuid4()
        person = type("PersonStub", (), {"id": person_id})()
        self.created_people.append(person)
        return person

    def assign_faces_to_person(self, *, face_ids, person_id):
        key = str(person_id)
        self.assignments[key] = [str(face_id) for face_id in face_ids]
        for face_id in face_ids:
            self.candidates_by_id.pop(face_id, None)
        return len(face_ids)

    @staticmethod
    def _uuid(value: str):
        from uuid import UUID

        return UUID(value)


class _FakeThumbnailService:
    def __init__(self) -> None:
        self.ensure_calls: list[str] = []

    def ensure_thumbnail(self, *, person_id):
        self.ensure_calls.append(str(person_id))


class PeopleClusteringServiceTest(unittest.TestCase):
    def _model(self, model_id: int = 17) -> AIModel:
        return AIModel(
            id=model_id,
            task=AI_MODEL_TASK_FACE_RECOGNITION,
            model_name="insightface-buffalo_l",
            version_tag="buffalo_l",
            vector_dimensions=512,
            is_deprecated=False,
        )

    def _candidate(self, *, confidence: float | None, crop_path: str | None) -> FaceClusterCandidate:
        return FaceClusterCandidate(
            id=uuid4(),
            face_model_id=17,
            confidence=confidence,
            crop_path=crop_path,
        )

    def test_creates_people_from_connected_components_and_skips_small_clusters(self) -> None:
        a = self._candidate(confidence=0.6, crop_path=None)
        b = self._candidate(confidence=0.9, crop_path="faces/b.webp")
        c = self._candidate(confidence=0.8, crop_path=None)
        d = self._candidate(confidence=0.7, crop_path=None)
        e = self._candidate(confidence=0.5, crop_path=None)
        model = self._model()
        repo = _FakePeopleClusteringRepository(
            candidates=[a, b, c, d, e],
            neighbors={
                (str(a.id), model.id): [str(b.id)],
                (str(b.id), model.id): [str(a.id), str(c.id)],
                (str(c.id), model.id): [str(b.id)],
                (str(d.id), model.id): [str(e.id)],
                (str(e.id), model.id): [str(d.id)],
            },
        )
        thumbnail_service = _FakeThumbnailService()
        service = PeopleClusteringService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=thumbnail_service,
        )

        summary = service.cluster_unassigned_faces(min_cluster_size=3)

        self.assertEqual(summary.candidates_seen, 5)
        self.assertEqual(summary.clusters_created, 1)
        self.assertEqual(summary.faces_assigned, 3)
        self.assertEqual(summary.skipped_small_clusters, 1)
        self.assertEqual(len(repo.created_people), 1)
        assigned_face_ids = next(iter(repo.assignments.values()))
        self.assertEqual(set(assigned_face_ids), {str(a.id), str(b.id), str(c.id)})
        self.assertEqual(
            thumbnail_service.ensure_calls,
            [str(repo.created_people[0].id)],
        )

    def test_rerun_skips_already_assigned_faces(self) -> None:
        a = self._candidate(confidence=0.6, crop_path=None)
        b = self._candidate(confidence=0.9, crop_path=None)
        model = self._model()
        repo = _FakePeopleClusteringRepository(
            candidates=[a, b],
            neighbors={
                (str(a.id), model.id): [str(b.id)],
                (str(b.id), model.id): [str(a.id)],
            },
        )
        thumbnail_service = _FakeThumbnailService()
        service = PeopleClusteringService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=thumbnail_service,
        )

        first = service.cluster_unassigned_faces()
        second = service.cluster_unassigned_faces()

        self.assertEqual(first.clusters_created, 1)
        self.assertEqual(first.faces_assigned, 2)
        self.assertEqual(second.candidates_seen, 0)
        self.assertEqual(second.clusters_created, 0)
        self.assertEqual(second.faces_assigned, 0)
        self.assertEqual(len(thumbnail_service.ensure_calls), 1)

    def test_uses_default_model_id_for_candidate_and_neighbor_queries(self) -> None:
        a = self._candidate(confidence=0.6, crop_path=None)
        b = self._candidate(confidence=0.7, crop_path=None)
        model = self._model(model_id=42)
        repo = _FakePeopleClusteringRepository(
            candidates=[a, b],
            neighbors={
                (str(a.id), model.id): [str(b.id)],
                (str(b.id), model.id): [str(a.id)],
            },
        )
        thumbnail_service = _FakeThumbnailService()
        service = PeopleClusteringService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=thumbnail_service,
        )

        service.cluster_unassigned_faces()

        self.assertTrue(repo.last_model_ids)
        self.assertTrue(all(model_id == 42 for model_id in repo.last_model_ids))

    def test_rejects_invalid_min_cluster_size(self) -> None:
        model = self._model()
        repo = _FakePeopleClusteringRepository(candidates=[], neighbors={})
        service = PeopleClusteringService(
            session=None,
            repository=repo,
            ai_model_repository=_FakeAIModelRepository(model),
            thumbnail_service=_FakeThumbnailService(),
        )

        with self.assertRaisesRegex(RuntimeError, "min_cluster_size"):
            service.cluster_unassigned_faces(min_cluster_size=1)


if __name__ == "__main__":
    unittest.main()
