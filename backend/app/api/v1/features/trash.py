from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import get_current_user
from app.models import Asset, User
from app.services.assets.urls import build_preview_url, build_thumbnail_url
from app.services.trash.schemas import (
    RestoredAssetDetailResponse,
    TrashAssetDetailResponse,
    TrashAssetItem,
    TrashAssetListResponse,
    TrashBulkRestoreRequest,
    TrashBulkRestoreResponse,
    TrashFaceSummary,
    TrashPersonSummary,
    TrashRestoreFailure,
    TrashRestoreJobSummary,
    TrashRestoreResponse,
    TrashSort,
    TrashTagSummary,
)
from app.services.trash.service import (
    TrashRestoreResult,
    TrashService,
    get_trash_service,
)

router = APIRouter()


def _thumbnail_url(request: Request, asset_id: UUID, variant: str) -> str:
    return build_thumbnail_url(str(request.base_url), asset_id, variant)


def _preview_url(request: Request, asset: Asset) -> str:
    return build_preview_url(str(request.base_url), asset)


def _build_tag_models(rows: list[dict[str, Any]] | None) -> list[TrashTagSummary]:
    return [TrashTagSummary.model_validate(row) for row in (rows or [])]


def _build_face_models(rows: list[dict[str, Any]] | None) -> list[TrashFaceSummary]:
    faces: list[TrashFaceSummary] = []
    for row in rows or []:
        person_id = row.get("person_id")
        person_name = row.get("person_name")
        faces.append(
            TrashFaceSummary(
                id=row["id"],
                person=TrashPersonSummary(id=person_id, name=person_name)
                if person_id or person_name
                else None,
            )
        )
    return faces


def _build_people_models(rows: list[dict[str, Any]] | None) -> list[TrashPersonSummary]:
    unique_people: dict[UUID, TrashPersonSummary] = {}
    for row in rows or []:
        person_id = row.get("person_id")
        if person_id is None or person_id in unique_people:
            continue
        unique_people[person_id] = TrashPersonSummary(
            id=person_id,
            name=row.get("person_name"),
        )
    return list(unique_people.values())


def _build_trash_item(
    request: Request,
    asset: Asset,
    tags: list[dict[str, Any]] | None,
    faces: list[dict[str, Any]] | None,
) -> TrashAssetItem:
    if asset.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deleted asset is missing deleted_at",
        )
    return TrashAssetItem(
        id=asset.id,
        deleted_at=asset.deleted_at,
        captured_at=asset.captured_at,
        description=asset.description,
        is_favorite=asset.is_favorite,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
        blurhash=asset.blurhash,
        tags=_build_tag_models(tags),
        faces=_build_face_models(faces),
    )


def _build_trash_detail(
    request: Request,
    asset: Asset,
    tags: list[dict[str, Any]] | None,
    faces: list[dict[str, Any]] | None,
) -> TrashAssetDetailResponse:
    if asset.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deleted asset is missing deleted_at",
        )
    return TrashAssetDetailResponse(
        id=asset.id,
        file_hash=asset.file_hash,
        master_path=asset.master_path,
        mime_type=asset.mime_type,
        deleted_at=asset.deleted_at,
        captured_at=asset.captured_at,
        captured_at_local=asset.captured_at_local,
        description=asset.description,
        is_favorite=asset.is_favorite,
        width=asset.width,
        height=asset.height,
        has_large_preview=asset.has_large_preview,
        file_size_bytes=asset.file_size_bytes,
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        duration_seconds=asset.duration_seconds,
        preview_status=asset.preview_status,
        blurhash=asset.blurhash,
        exif_data=asset.exif_data,
        tags=_build_tag_models(tags),
        people=_build_people_models(faces),
        faces=_build_face_models(faces),
        small_thumbnail_url=_thumbnail_url(request, asset.id, "small"),
        preview_url=_preview_url(request, asset),
        created_at=asset.created_at,
    )


def _build_restore_response(
    request: Request,
    result: TrashRestoreResult,
) -> TrashRestoreResponse:
    return TrashRestoreResponse(
        asset=RestoredAssetDetailResponse(
            id=result.asset.id,
            file_hash=result.asset.file_hash,
            master_path=result.asset.master_path,
            mime_type=result.asset.mime_type,
            captured_at=result.asset.captured_at,
            captured_at_local=result.asset.captured_at_local,
            description=result.asset.description,
            is_favorite=result.asset.is_favorite,
            width=result.asset.width,
            height=result.asset.height,
            has_large_preview=result.asset.has_large_preview,
            file_size_bytes=result.asset.file_size_bytes,
            video_codec=result.asset.video_codec,
            audio_codec=result.asset.audio_codec,
            duration_seconds=result.asset.duration_seconds,
            preview_status=result.asset.preview_status,
            blurhash=result.asset.blurhash,
            exif_data=result.asset.exif_data,
            tags=_build_tag_models(result.tags),
            people=_build_people_models(result.faces),
            faces=_build_face_models(result.faces),
            small_thumbnail_url=_thumbnail_url(request, result.asset.id, "small"),
            preview_url=_preview_url(request, result.asset),
            created_at=result.asset.created_at,
        ),
        jobs=TrashRestoreJobSummary(
            queued_metadata_job=result.jobs.queued_metadata_job,
            queued_embedding_job=result.jobs.queued_embedding_job,
            queued_face_job=result.jobs.queued_face_job,
            ran_face_matching=result.jobs.ran_face_matching,
            matched_faces=result.jobs.matched_faces,
        ),
    )


@router.get("/assets", response_model=TrashAssetListResponse, include_in_schema=False)
@router.get("/assets/", response_model=TrashAssetListResponse)
def list_deleted_assets(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: TrashSort = Query(default="deleted_at_desc"),
    trash_service: TrashService = Depends(get_trash_service),
    current_user: User = Depends(get_current_user),
) -> TrashAssetListResponse:
    del current_user
    total, rows = trash_service.list_deleted_assets(
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return TrashAssetListResponse(
        items=[
            _build_trash_item(request, asset, tags, faces)
            for asset, tags, faces in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/assets/{asset_id}", response_model=TrashAssetDetailResponse)
def get_deleted_asset(
    asset_id: UUID,
    request: Request,
    trash_service: TrashService = Depends(get_trash_service),
    current_user: User = Depends(get_current_user),
) -> TrashAssetDetailResponse:
    del current_user
    asset, tags, faces = trash_service.get_deleted_asset_detail(asset_id)
    return _build_trash_detail(request, asset, tags, faces)


@router.post("/assets/{asset_id}/restore", response_model=TrashRestoreResponse)
async def restore_deleted_asset(
    asset_id: UUID,
    request: Request,
    trash_service: TrashService = Depends(get_trash_service),
    current_user: User = Depends(get_current_user),
) -> TrashRestoreResponse:
    del current_user
    result = await trash_service.restore_asset(asset_id)
    return _build_restore_response(request, result)


@router.post("/assets/restore", response_model=TrashBulkRestoreResponse)
async def restore_deleted_assets(
    payload: TrashBulkRestoreRequest,
    request: Request,
    trash_service: TrashService = Depends(get_trash_service),
    current_user: User = Depends(get_current_user),
) -> TrashBulkRestoreResponse:
    del current_user
    restored, failures = await trash_service.restore_assets(payload.asset_ids)
    return TrashBulkRestoreResponse(
        requested=len(payload.asset_ids),
        restored=len(restored),
        failed=len(failures),
        items=[_build_restore_response(request, item) for item in restored],
        failures=[
            TrashRestoreFailure(asset_id=asset_id, detail=detail)
            for asset_id, detail in failures
        ],
    )
