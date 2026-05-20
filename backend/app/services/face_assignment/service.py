from __future__ import annotations

from dataclasses import dataclass
from math import inf
from uuid import UUID

from sqlmodel import Session

from app.services.ai_models.repository import (
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.face_assignment.repository import (
    FaceAssignmentNeighbor,
    FaceAssignmentRepository,
)
from app.services.people.thumbnails import PersonThumbnailService

ASSIGNMENT_DISTANCE_THRESHOLD = 0.40
ASSIGNMENT_TOP_K = 30
ASSIGNMENT_MIN_SUPPORT = 2
ASSIGNMENT_DISTANCE_MARGIN = 0.05


class FaceAssignmentServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchedFaceAssignment:
    face_id: UUID
    person_id: UUID
    distance: float


@dataclass(frozen=True)
class FaceAssignmentDecision:
    person_id: UUID | None
    distance: float | None
    support_count: int


@dataclass(frozen=True)
class FaceAssignmentResult:
    asset_id: UUID
    faces_seen: int
    faces_matched: int
    faces_unmatched: int
    assignments: list[MatchedFaceAssignment]


class FaceAssignmentService:
    def __init__(
        self,
        session: Session,
        *,
        repository: FaceAssignmentRepository | None = None,
        ai_model_repository: AIModelRepository | None = None,
        thumbnail_service: PersonThumbnailService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or FaceAssignmentRepository(session)
        self.ai_model_repository = ai_model_repository or AIModelRepository(session)
        self.thumbnail_service = thumbnail_service or PersonThumbnailService(session)

    def assign_faces_for_asset(
        self,
        asset_id: UUID,
        *,
        threshold: float = ASSIGNMENT_DISTANCE_THRESHOLD,
        top_k: int = ASSIGNMENT_TOP_K,
        min_support: int = ASSIGNMENT_MIN_SUPPORT,
        margin: float = ASSIGNMENT_DISTANCE_MARGIN,
    ) -> FaceAssignmentResult:
        if top_k < 1:
            raise FaceAssignmentServiceError("top_k must be at least 1")
        if min_support < 1:
            raise FaceAssignmentServiceError("min_support must be at least 1")
        if threshold < 0:
            raise FaceAssignmentServiceError("threshold must be non-negative")
        if margin < 0:
            raise FaceAssignmentServiceError("margin must be non-negative")

        try:
            default_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError as exc:
            raise FaceAssignmentServiceError(str(exc)) from exc

        candidates = self.repository.list_assignment_candidates(
            asset_id=asset_id,
            model_id=default_model.id,
        )
        assignments: list[MatchedFaceAssignment] = []
        touched_person_ids: set[UUID] = set()

        for candidate in candidates:
            neighbors = self.repository.list_reference_neighbors(
                face_id=candidate.id,
                model_id=default_model.id,
                distance_threshold=threshold,
                top_k=top_k,
            )
            decision = self._choose_person(
                neighbors=neighbors,
                threshold=threshold,
                min_support=min_support,
                margin=margin,
            )
            if decision.person_id is None or decision.distance is None:
                continue
            assigned = self.repository.assign_face_to_person(
                face_id=candidate.id,
                person_id=decision.person_id,
            )
            if not assigned:
                continue
            touched_person_ids.add(decision.person_id)
            assignments.append(
                MatchedFaceAssignment(
                    face_id=candidate.id,
                    person_id=decision.person_id,
                    distance=decision.distance,
                )
            )

        for person_id in sorted(touched_person_ids, key=str):
            self.thumbnail_service.ensure_thumbnail(person_id=person_id)

        return FaceAssignmentResult(
            asset_id=asset_id,
            faces_seen=len(candidates),
            faces_matched=len(assignments),
            faces_unmatched=len(candidates) - len(assignments),
            assignments=assignments,
        )

    @staticmethod
    def _choose_person(
        *,
        neighbors: list[FaceAssignmentNeighbor],
        threshold: float,
        min_support: int,
        margin: float,
    ) -> FaceAssignmentDecision:
        if not neighbors:
            return FaceAssignmentDecision(
                person_id=None, distance=None, support_count=0
            )

        grouped: dict[UUID, tuple[int, float]] = {}
        for neighbor in neighbors:
            count, best_distance = grouped.get(neighbor.person_id, (0, inf))
            grouped[neighbor.person_id] = (
                count + 1,
                min(best_distance, neighbor.distance),
            )

        ranked = sorted(
            grouped.items(),
            key=lambda item: (item[1][1], -item[1][0], str(item[0])),
        )
        best_person_id, (best_support, best_distance) = ranked[0]
        if best_distance > threshold or best_support < min_support:
            return FaceAssignmentDecision(
                person_id=None,
                distance=None,
                support_count=best_support,
            )

        second_distance = ranked[1][1][1] if len(ranked) > 1 else inf
        if second_distance - best_distance < margin:
            return FaceAssignmentDecision(
                person_id=None,
                distance=None,
                support_count=best_support,
            )

        return FaceAssignmentDecision(
            person_id=best_person_id,
            distance=best_distance,
            support_count=best_support,
        )
