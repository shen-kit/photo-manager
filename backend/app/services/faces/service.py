from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from sqlmodel import Session

from app.models import Asset, Face
from app.services.ai_models.repository import (
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.assets.media import (
    is_supported_image_mime_type,
    master_path_to_source_path,
)
from app.services.face_detection.service import (
    DetectedFace,
    FaceDetectionError,
    detect_faces,
)
from app.services.faces.repository import FaceRepository
from app.services.people.thumbnails import PersonThumbnailService

logger = logging.getLogger(__name__)


class FaceProcessingServiceError(RuntimeError):
    pass


class FaceManagementServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceProcessingResult:
    asset_id: UUID
    model_id: int
    processed: bool
    skipped: bool
    faces_created: int
    detected_faces: int
    deleted_unconfirmed_faces: int


class FaceProcessingService:
    def __init__(
        self,
        session: Session,
        *,
        repository: FaceRepository | None = None,
        ai_model_repository: AIModelRepository | None = None,
        detector: Callable[[Path], list[DetectedFace]] = detect_faces,
    ) -> None:
        self.session = session
        self.repository = repository or FaceRepository(session)
        self.ai_model_repository = ai_model_repository or AIModelRepository(session)
        self.detector = detector

    def process_asset_faces(
        self,
        asset_id: UUID,
        *,
        force: bool = False,
    ) -> FaceProcessingResult:
        try:
            face_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError as exc:
            raise FaceProcessingServiceError(str(exc)) from exc

        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise FaceProcessingServiceError(f"Asset {asset_id} not found")
        if asset.deleted_at is not None:
            raise FaceProcessingServiceError(f"Asset {asset_id} is deleted")
        if not is_supported_image_mime_type(asset.mime_type):
            logger.info("Skipping face processing for unsupported asset %s", asset.id)
            return FaceProcessingResult(
                asset_id=asset.id,
                model_id=face_model.id,
                processed=False,
                skipped=True,
                faces_created=0,
                detected_faces=0,
                deleted_unconfirmed_faces=0,
            )

        total_existing = self.repository.count_faces(
            asset_id=asset.id,
            model_id=face_model.id,
        )
        confirmed_existing = self.repository.count_confirmed_faces(
            asset_id=asset.id,
            model_id=face_model.id,
        )
        if not force and total_existing > 0:
            return FaceProcessingResult(
                asset_id=asset.id,
                model_id=face_model.id,
                processed=False,
                skipped=True,
                faces_created=0,
                detected_faces=0,
                deleted_unconfirmed_faces=0,
            )
        if force and total_existing > 0 and confirmed_existing == total_existing:
            return FaceProcessingResult(
                asset_id=asset.id,
                model_id=face_model.id,
                processed=False,
                skipped=True,
                faces_created=0,
                detected_faces=0,
                deleted_unconfirmed_faces=0,
            )

        source_path = self._resolve_source_path(asset)
        try:
            detected_faces = self.detector(source_path)
        except FaceDetectionError as exc:
            raise FaceProcessingServiceError(str(exc)) from exc

        confirmed_boxes = {
            self._bounding_box_key(box)
            for box in self.repository.list_confirmed_bounding_boxes(
                asset_id=asset.id,
                model_id=face_model.id,
            )
        }
        filtered_faces = [
            face
            for face in detected_faces
            if self._bounding_box_key(self._bounding_box_dict(face))
            not in confirmed_boxes
        ]

        deleted_unconfirmed_faces = 0
        if force:
            deleted_unconfirmed_faces = self.repository.delete_unconfirmed_faces(
                asset_id=asset.id,
                model_id=face_model.id,
            )

        face_rows = [
            self._build_face_row(
                asset_id=asset.id,
                model_id=face_model.id,
                detected_face=detected_face,
            )
            for detected_face in filtered_faces
        ]
        self.repository.insert_faces(faces=face_rows)

        return FaceProcessingResult(
            asset_id=asset.id,
            model_id=face_model.id,
            processed=True,
            skipped=False,
            faces_created=len(face_rows),
            detected_faces=len(detected_faces),
            deleted_unconfirmed_faces=deleted_unconfirmed_faces,
        )

    def count_assets_pending_face_processing(
        self,
        *,
        force: bool = False,
    ) -> tuple[int, int]:
        try:
            face_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError as exc:
            raise FaceProcessingServiceError(str(exc)) from exc
        total = self.repository.count_assets_pending_face_processing(
            model_id=face_model.id,
            force=force,
        )
        return face_model.id, total

    def list_asset_ids_pending_face_processing(
        self,
        *,
        force: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[int, list[UUID]]:
        try:
            face_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_FACE_RECOGNITION
            )
        except AIModelConfigurationError as exc:
            raise FaceProcessingServiceError(str(exc)) from exc
        asset_ids = self.repository.list_asset_ids_pending_face_processing(
            model_id=face_model.id,
            force=force,
            limit=limit,
            offset=offset,
        )
        return face_model.id, asset_ids

    def _resolve_source_path(self, asset: Asset) -> Path:
        try:
            source_path = master_path_to_source_path(asset.master_path)
        except ValueError as exc:
            raise FaceProcessingServiceError(
                f"Invalid master path for asset {asset.id}"
            ) from exc
        if not source_path.is_file():
            raise FaceProcessingServiceError(
                f"Source file missing for asset {asset.id}"
            )
        return source_path

    def _build_face_row(
        self,
        *,
        asset_id: UUID,
        model_id: int,
        detected_face: DetectedFace,
    ) -> Face:
        return Face(
            asset_id=asset_id,
            face_model_id=model_id,
            bounding_box=self._bounding_box_dict(detected_face),
            confidence=detected_face.confidence,
            embedding=detected_face.embedding,
            crop_path=None,
            is_confirmed=False,
            is_excluded=False,
        )

    @staticmethod
    def _bounding_box_key(
        box: dict[str, object],
    ) -> tuple[int, int, int, int, int, int]:
        return (
            int(box.get("x", 0)),
            int(box.get("y", 0)),
            int(box.get("width", 0)),
            int(box.get("height", 0)),
            int(box.get("image_width", 0)),
            int(box.get("image_height", 0)),
        )

    @staticmethod
    def _bounding_box_dict(face: DetectedFace) -> dict[str, int]:
        box = face.bounding_box
        return {
            "x": box.x,
            "y": box.y,
            "width": box.width,
            "height": box.height,
            "image_width": box.image_width,
            "image_height": box.image_height,
        }


class FaceManagementService:
    def __init__(
        self,
        session: Session,
        *,
        repository: FaceRepository | None = None,
        thumbnail_service: PersonThumbnailService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or FaceRepository(session)
        self.thumbnail_service = thumbnail_service or PersonThumbnailService(session)

    def update_face(
        self,
        face_id: UUID,
        *,
        person_id: UUID | None | object = ...,
        is_confirmed: bool | None | object = ...,
        is_excluded: bool | None | object = ...,
    ) -> Face:
        face = self.repository.get_face(face_id)
        if face is None:
            raise FaceManagementServiceError(f"Face {face_id} not found")
        previous_person_id = face.person_id

        current_excluded = face.is_excluded
        assigned_person_id = person_id if person_id is not ... else face.person_id
        resulting_excluded = (
            is_excluded if is_excluded is not ... else current_excluded
        )

        if person_id is not ... and person_id is not None:
            person = self.repository.get_person(person_id)
            if person is None:
                raise FaceManagementServiceError(f"Person {person_id} not found")
            if current_excluded and is_excluded is not False:
                raise FaceManagementServiceError(
                    "Excluded face cannot be assigned without explicitly unexcluding it"
                )

        if assigned_person_id is not None and resulting_excluded:
            raise FaceManagementServiceError(
                "Excluded face cannot remain assigned to a person"
            )

        if person_id is not ...:
            face.person_id = person_id
        if is_excluded is not ...:
            face.is_excluded = bool(is_excluded)
        if is_confirmed is not ...:
            face.is_confirmed = bool(is_confirmed)
        elif assigned_person_id is not None:
            face.is_confirmed = True

        updated_face = self.repository.update_face(face)
        impacted_person_ids = {
            person_id
            for person_id in {previous_person_id, updated_face.person_id}
            if person_id is not None
        }
        for impacted_person_id in impacted_person_ids:
            self.thumbnail_service.ensure_thumbnail(person_id=impacted_person_id)
        return updated_face
