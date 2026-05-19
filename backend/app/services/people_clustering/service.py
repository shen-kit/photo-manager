from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.services.ai_models.repository import (
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.people_clustering.repository import (
    FaceClusterCandidate,
    PeopleClusteringRepository,
)
from app.services.people.thumbnails import PersonThumbnailService

CLUSTER_DISTANCE_THRESHOLD = 0.4
CLUSTER_TOP_K = 30
CLUSTER_MIN_SIZE = 2


class PeopleClusteringServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PeopleClusteringSummary:
    candidates_seen: int
    clusters_created: int
    faces_assigned: int
    skipped_small_clusters: int


@dataclass(frozen=True)
class ExistingPersonResolution:
    person_id: UUID | None
    ambiguous: bool = False


class PeopleClusteringService:
    def __init__(
        self,
        session: Session,
        *,
        repository: PeopleClusteringRepository | None = None,
        ai_model_repository: AIModelRepository | None = None,
        thumbnail_service: PersonThumbnailService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or PeopleClusteringRepository(session)
        self.ai_model_repository = ai_model_repository or AIModelRepository(session)
        self.thumbnail_service = thumbnail_service or PersonThumbnailService(session)

    def cluster_unassigned_faces(
        self,
        *,
        distance_threshold: float = CLUSTER_DISTANCE_THRESHOLD,
        top_k: int = CLUSTER_TOP_K,
        min_cluster_size: int = CLUSTER_MIN_SIZE,
    ) -> PeopleClusteringSummary:
        if top_k < 1:
            raise PeopleClusteringServiceError("top_k must be at least 1")
        if min_cluster_size < 2:
            raise PeopleClusteringServiceError("min_cluster_size must be at least 2")
        if distance_threshold < 0:
            raise PeopleClusteringServiceError(
                "distance_threshold must be non-negative"
            )

        try:
            default_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError as exc:
            raise PeopleClusteringServiceError(str(exc)) from exc

        candidates = self.repository.list_cluster_candidates(model_id=default_model.id)
        candidate_ids = {candidate.id for candidate in candidates}
        adjacency = self._build_adjacency(
            candidates=candidates,
            candidate_ids=candidate_ids,
            model_id=default_model.id,
            distance_threshold=distance_threshold,
            top_k=top_k,
        )
        components = self._connected_components(candidate_ids, adjacency)

        clusters_created = 0
        faces_assigned = 0
        skipped_small_clusters = 0

        for component in components:
            existing_person = self._resolve_existing_person_id(
                component=component,
                model_id=default_model.id,
                distance_threshold=distance_threshold,
                top_k=top_k,
            )
            if existing_person.person_id is not None:
                ordered_face_ids = sorted(component, key=str)
                faces_assigned += self.repository.assign_faces_to_person(
                    face_ids=ordered_face_ids,
                    person_id=existing_person.person_id,
                )
                self.thumbnail_service.ensure_thumbnail(
                    person_id=existing_person.person_id
                )
                continue
            if existing_person.ambiguous:
                continue
            if len(component) < min_cluster_size:
                skipped_small_clusters += 1
                continue
            ordered_face_ids = sorted(component, key=str)
            person = self.repository.create_person()
            faces_assigned += self.repository.assign_faces_to_person(
                face_ids=ordered_face_ids,
                person_id=person.id,
            )
            self.thumbnail_service.ensure_thumbnail(person_id=person.id)
            clusters_created += 1

        return PeopleClusteringSummary(
            candidates_seen=len(candidates),
            clusters_created=clusters_created,
            faces_assigned=faces_assigned,
            skipped_small_clusters=skipped_small_clusters,
        )

    def _build_adjacency(
        self,
        *,
        candidates: list[FaceClusterCandidate],
        candidate_ids: set[UUID],
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> dict[UUID, set[UUID]]:
        adjacency: dict[UUID, set[UUID]] = defaultdict(set)
        for candidate in candidates:
            neighbors = self.repository.list_neighbor_face_ids(
                face_id=candidate.id,
                model_id=model_id,
                distance_threshold=distance_threshold,
                top_k=top_k,
            )
            for neighbor_id in neighbors:
                if neighbor_id not in candidate_ids:
                    continue
                adjacency[candidate.id].add(neighbor_id)
                adjacency[neighbor_id].add(candidate.id)
        return adjacency

    @staticmethod
    def _connected_components(
        candidate_ids: set[UUID],
        adjacency: dict[UUID, set[UUID]],
    ) -> list[set[UUID]]:
        remaining = set(candidate_ids)
        components: list[set[UUID]] = []

        while remaining:
            root = remaining.pop()
            stack = [root]
            component = {root}
            while stack:
                node = stack.pop()
                for neighbor in adjacency.get(node, set()):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        stack.append(neighbor)
            components.append(component)

        return components

    def _resolve_existing_person_id(
        self,
        *,
        component: set[UUID],
        model_id: int,
        distance_threshold: float,
        top_k: int,
    ) -> ExistingPersonResolution:
        person_scores: dict[UUID, tuple[int, float]] = {}
        for face_id in component:
            for person_id, distance in self.repository.list_labeled_neighbor_people(
                face_id=face_id,
                model_id=model_id,
                distance_threshold=distance_threshold,
                top_k=top_k,
            ):
                count, best_distance = person_scores.get(person_id, (0, float("inf")))
                person_scores[person_id] = (count + 1, min(best_distance, distance))

        if not person_scores:
            return ExistingPersonResolution(person_id=None, ambiguous=False)
        if len(person_scores) != 1:
            return ExistingPersonResolution(person_id=None, ambiguous=True)
        return ExistingPersonResolution(
            person_id=next(iter(person_scores)),
            ambiguous=False,
        )
