from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import get_current_user
from app.models import Face, User
from app.services.face_assignment.service import (
    FaceAssignmentService,
    FaceAssignmentServiceError,
)
from app.services.faces.query import FaceQueryService, get_face_query_service
from app.services.faces.schemas import (
    AssetFaceMatchRead,
    AssetFaceRead,
    FaceBoundingBoxRead,
    FaceMatchAssignmentRead,
    FaceUpdateRequest,
)
from app.services.faces.service import FaceManagementService, FaceManagementServiceError
from app.services.jobs.dispatcher import (
    INTENT_INTERACTIVE,
    JobDispatcher,
    PROCESS_ASSET_FACES_JOB_NAME,
    faces_dedup_key,
)
from app.services.ai_models.repository import AI_MODEL_TASK_FACE_RECOGNITION
from app.services.jobs.queue import resolve_default_model_id
from app.services.jobs.schemas import JobRead

router = APIRouter()


def _crop_url(request: Request, crop_path: str | None) -> str | None:
    if not crop_path:
        return None
    normalized = Path(crop_path).as_posix().lstrip("/")
    return str(request.base_url).rstrip("/") + f"/media/processed/{normalized}"


def _build_face_response(request: Request, face: Face) -> AssetFaceRead:
    bounding_box = None
    if isinstance(face.bounding_box, dict):
        bounding_box = FaceBoundingBoxRead.model_validate(face.bounding_box)
    return AssetFaceRead(
        id=face.id,
        asset_id=face.asset_id,
        person_id=face.person_id,
        bounding_box=bounding_box,
        detection_confidence=face.confidence,
        crop_path=face.crop_path,
        crop_url=_crop_url(request, face.crop_path),
        is_confirmed=face.is_confirmed,
        is_excluded=face.is_excluded,
        created_at=face.created_at,
        updated_at=face.updated_at,
    )


@router.post(
    "/assets/{asset_id}/faces/process",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_asset_faces(
    asset_id: UUID,
    force: bool = Query(default=False),
    auto_match: bool = Query(default=True),
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    current_user: User = Depends(get_current_user),
) -> JobRead:
    del current_user
    face_query_service.require_active_asset(asset_id)
    dispatch = await JobDispatcher(face_query_service.session).dispatch(
        job_name=PROCESS_ASSET_FACES_JOB_NAME,
        args=[str(asset_id), force, auto_match, None],
        type=PROCESS_ASSET_FACES_JOB_NAME,
        parameters={
            "asset_id": str(asset_id),
            "force": force,
            "auto_match": auto_match,
        },
        intent=INTENT_INTERACTIVE,
        dedup_key=faces_dedup_key(
            asset_id,
            model_id=resolve_default_model_id(AI_MODEL_TASK_FACE_RECOGNITION),
            auto_match=auto_match,
        ),
        related_asset_id=asset_id,
        is_visible=True,
        force=force,
    )
    return JobRead.model_validate(dispatch.job, from_attributes=True)


@router.post(
    "/assets/{asset_id}/faces/match",
    response_model=AssetFaceMatchRead,
)
def match_asset_faces(
    asset_id: UUID,
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    current_user: User = Depends(get_current_user),
) -> AssetFaceMatchRead:
    del current_user
    face_query_service.require_active_asset(asset_id)
    try:
        result = FaceAssignmentService(
            face_query_service.session
        ).assign_faces_for_asset(asset_id)
    except FaceAssignmentServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return AssetFaceMatchRead(
        asset_id=result.asset_id,
        faces_seen=result.faces_seen,
        faces_matched=result.faces_matched,
        faces_unmatched=result.faces_unmatched,
        assignments=[
            FaceMatchAssignmentRead(
                face_id=assignment.face_id,
                person_id=assignment.person_id,
                distance=assignment.distance,
            )
            for assignment in result.assignments
        ],
    )


@router.get(
    "/assets/{asset_id}/faces",
    response_model=list[AssetFaceRead],
)
def list_asset_faces(
    asset_id: UUID,
    request: Request,
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    current_user: User = Depends(get_current_user),
) -> list[AssetFaceRead]:
    del current_user
    faces = face_query_service.list_faces_for_asset(asset_id)
    return [_build_face_response(request, face) for face in faces]


@router.patch("/faces/{face_id}", response_model=AssetFaceRead)
def update_face(
    face_id: UUID,
    payload: FaceUpdateRequest,
    request: Request,
    face_query_service: FaceQueryService = Depends(get_face_query_service),
    current_user: User = Depends(get_current_user),
) -> AssetFaceRead:
    del current_user
    updates = payload.model_dump(exclude_unset=True)
    try:
        face = FaceManagementService(face_query_service.session).update_face(
            face_id,
            **updates,
        )
    except FaceManagementServiceError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=detail
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=detail
        ) from exc
    return _build_face_response(request, face)
