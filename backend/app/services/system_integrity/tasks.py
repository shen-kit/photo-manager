from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.models import Asset
from app.services.assets.batching import ThumbnailBatchProcessor
from app.services.assets.media import MEDIA_PROCESSED_DIR, processed_asset_dir, processed_video_preview_path
from app.services.assets.preview import AssetPreviewService
from app.services.embeddings.service import EmbeddingService
from app.services.faces.service import FaceProcessingService
from app.services.jobs.service import JobService
from app.services.people.repository import PeopleRepository
from app.services.people.thumbnails import PersonThumbnailService
from app.services.system_integrity.definitions import (
    CHECK_ASSET_DERIVATIVES,
    CHECK_CLIP_EMBEDDINGS,
    CHECK_FACE_PROCESSING,
    CHECK_ORIGINALS_EXIST,
    CHECK_ORIGINAL_FILES_WITHOUT_DB_ASSETS,
    CHECK_PEOPLE_WITHOUT_ACTIVE_FACES,
    CHECK_PROCESSED_FILES_WITHOUT_DB_ASSETS,
    REPAIR_ASSET_DERIVATIVES,
    REPAIR_CLIP_EMBEDDINGS,
    REPAIR_FACE_PROCESSING,
    REPAIR_PEOPLE_WITHOUT_ACTIVE_FACES,
    REPAIR_PROCESSED_ORPHAN_FILES,
)
from app.services.system_integrity.diagnostics import (
    DiagnosticEvaluation,
    _expected_processed_paths,
    evaluate_check_asset_derivatives,
    evaluate_check_clip_embeddings,
    evaluate_check_face_processing,
    evaluate_check_original_files_without_db_assets,
    evaluate_check_originals_exist,
    evaluate_check_people_without_active_faces,
    evaluate_check_processed_files_without_db_assets,
)
from app.services.system_integrity.service import SystemIntegrityService

logger = logging.getLogger(__name__)


def _evaluate(session: Session, diagnostic_key: str) -> DiagnosticEvaluation:
    if diagnostic_key == CHECK_ORIGINALS_EXIST:
        return evaluate_check_originals_exist(session)
    if diagnostic_key == CHECK_ASSET_DERIVATIVES:
        return evaluate_check_asset_derivatives(session)
    if diagnostic_key == CHECK_CLIP_EMBEDDINGS:
        return evaluate_check_clip_embeddings(session)
    if diagnostic_key == CHECK_FACE_PROCESSING:
        return evaluate_check_face_processing(session)
    if diagnostic_key == CHECK_ORIGINAL_FILES_WITHOUT_DB_ASSETS:
        return evaluate_check_original_files_without_db_assets(session)
    if diagnostic_key == CHECK_PROCESSED_FILES_WITHOUT_DB_ASSETS:
        return evaluate_check_processed_files_without_db_assets(session)
    if diagnostic_key == CHECK_PEOPLE_WITHOUT_ACTIVE_FACES:
        return evaluate_check_people_without_active_faces(session)
    raise RuntimeError(f"Unsupported diagnostic key: {diagnostic_key}")


async def run_system_integrity_diagnostic(
    _: dict[str, object],
    run_id: str,
) -> None:
    run_uuid = UUID(run_id)
    with Session(engine) as session:
        service = SystemIntegrityService(session)
        run = service.mark_run_started(run_uuid)
        job_service = JobService(session)
        if run.related_job_id is not None:
            job_service.mark_running(
                run.related_job_id,
                message=f"Running diagnostic {run.diagnostic_key}",
            )
        try:
            evaluation = _evaluate(session, run.diagnostic_key)
            sample_items = evaluation.items[:20]
            service.store_items(run_id=run_uuid, items=evaluation.items)
            completed_run = service.mark_run_completed(
                run_uuid,
                health_state=evaluation.health_state,
                summary_json=evaluation.summary,
                sample_items_json={
                    "items": sample_items,
                    "sample_count": len(sample_items),
                },
            )
            if completed_run.related_job_id is not None:
                job_service.complete_job(
                    completed_run.related_job_id,
                    result={
                        "diagnostic_run_id": str(completed_run.id),
                        "diagnostic_key": completed_run.diagnostic_key,
                        "health_state": completed_run.health_state,
                        "summary": completed_run.summary_json,
                    },
                    message=f"Completed diagnostic {completed_run.diagnostic_key}",
                )
        except Exception as exc:
            logger.exception(
                "System integrity diagnostic %s failed for run %s",
                run.diagnostic_key,
                run_id,
            )
            failed_run = service.mark_run_failed(run_uuid, error_message=str(exc))
            if failed_run.related_job_id is not None:
                job_service.fail_job(failed_run.related_job_id, str(exc))
            raise


async def run_system_integrity_repair(
    _: dict[str, object],
    diagnostic_run_id: str,
) -> None:
    run_uuid = UUID(diagnostic_run_id)
    with Session(engine) as session:
        service = SystemIntegrityService(session)
        job_service = JobService(session)
        run = service.get_run_model(run_uuid)
        if run.latest_repair_job_id is not None:
            job_service.mark_running(
                run.latest_repair_job_id,
                message=f"Running repair for {run.diagnostic_key}",
            )
        items = service.repository.list_run_items(diagnostic_run_id=run_uuid, limit=None)
        try:
            result = _repair_items(session, run.repair_job_key, items)
            if run.latest_repair_job_id is not None:
                job_service.complete_job(
                    run.latest_repair_job_id,
                    result=result,
                    message=f"Completed repair for {run.diagnostic_key}",
                )
        except Exception as exc:
            if run.latest_repair_job_id is not None:
                job_service.fail_job(run.latest_repair_job_id, str(exc))
            raise


def _repair_items(session: Session, repair_job_key: str | None, items) -> dict[str, int]:
    if repair_job_key is None:
        raise RuntimeError("Diagnostic does not support repair")
    processed_count = 0
    repaired_count = 0
    skipped_count = 0
    failed_count = 0
    for item in items:
        processed_count += 1
        try:
            repaired = _repair_item(session, repair_job_key, item)
        except Exception:
            failed_count += 1
            continue
        if repaired:
            repaired_count += 1
        else:
            skipped_count += 1
    return {
        "processed_count": processed_count,
        "repaired_count": repaired_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
    }


def _repair_item(session: Session, repair_job_key: str, item) -> bool:
    if repair_job_key == REPAIR_CLIP_EMBEDDINGS:
        return _repair_clip_embedding(session, item.asset_id)
    if repair_job_key == REPAIR_FACE_PROCESSING:
        return _repair_face_processing(session, item.asset_id)
    if repair_job_key == REPAIR_ASSET_DERIVATIVES:
        return _repair_asset_derivatives(session, item.asset_id)
    if repair_job_key == REPAIR_PROCESSED_ORPHAN_FILES:
        return _repair_processed_orphan_file(session, item.relative_path)
    if repair_job_key == REPAIR_PEOPLE_WITHOUT_ACTIVE_FACES:
        return _repair_person_without_active_faces(session, item.person_id)
    raise RuntimeError(f"Unsupported repair job key: {repair_job_key}")


def _repair_clip_embedding(session: Session, asset_id: UUID | None) -> bool:
    if asset_id is None:
        return False
    result = EmbeddingService(session).generate_for_asset(asset_id, force=False)
    return result.generated


def _repair_face_processing(session: Session, asset_id: UUID | None) -> bool:
    if asset_id is None:
        return False
    result = FaceProcessingService(session).process_asset_faces(asset_id, force=False)
    return result.processed


def _repair_asset_derivatives(session: Session, asset_id: UUID | None) -> bool:
    if asset_id is None:
        return False
    asset = session.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None:
        return False
    asset_dir = processed_asset_dir(asset.id)
    missing_before: list[str] = []
    if not (asset_dir / "tiny.webp").is_file():
        missing_before.append("tiny")
    if not (asset_dir / "small.webp").is_file():
        missing_before.append("small")
    if asset.has_large_preview and not (asset_dir / "large.webp").is_file():
        missing_before.append("large")
    if asset.media_kind == "video" and not processed_video_preview_path(asset.id).is_file():
        missing_before.append("video_preview")
    if not missing_before:
        return False
    repaired = False
    ThumbnailBatchProcessor(session).ensure_asset_thumbnails(asset_id)
    if asset.media_kind == "video":
        preview_path = processed_video_preview_path(asset.id)
        if not preview_path.is_file():
            AssetPreviewService(session).generate_video_preview(asset.id)
            repaired = True
    elif asset.has_large_preview:
        preview_path = asset_dir / "large.webp"
        if not preview_path.is_file():
            AssetPreviewService(session).generate_image_preview(asset.id)
            repaired = True
    return repaired or all(
        [
            (asset_dir / "tiny.webp").is_file(),
            (asset_dir / "small.webp").is_file(),
            (not asset.has_large_preview) or (asset_dir / "large.webp").is_file(),
            (asset.media_kind != "video") or processed_video_preview_path(asset.id).is_file(),
        ]
    )


def _repair_processed_orphan_file(session: Session, relative_path: str | None) -> bool:
    if not relative_path:
        return False
    if relative_path in _expected_processed_paths(session):
        return False
    resolved = (MEDIA_PROCESSED_DIR / relative_path).resolve()
    try:
        resolved.relative_to(MEDIA_PROCESSED_DIR)
    except ValueError as exc:
        raise RuntimeError("Processed path escapes media root") from exc
    if not resolved.is_file():
        return False
    resolved.unlink(missing_ok=True)
    return True


def _repair_person_without_active_faces(session: Session, person_id: UUID | None) -> bool:
    if person_id is None:
        return False
    people_repository = PeopleRepository(session)
    if people_repository.list_person_ids_without_active_assets(person_ids=[person_id]) != [
        person_id
    ]:
        return False
    person = people_repository.get_person(person_id)
    if person is None:
        return False
    PersonThumbnailService(session).delete_thumbnail_file(person.thumbnail_path)
    people_repository.delete_people([person])
    return True
