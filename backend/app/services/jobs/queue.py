from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from app.core.database import engine
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.jobs.dispatcher import (
    GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
    GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME,
    GENERATE_ASSET_PREVIEW_JOB_NAME,
    INTENT_AI,
    INTENT_BACKFILL,
    INTENT_INTERACTIVE,
    INTENT_MAINTENANCE,
    INTENT_METADATA,
    INTENT_PREVIEW,
    PROCESS_ASSET_FACES_BATCH_JOB_NAME,
    PROCESS_ASSET_FACES_JOB_NAME,
    PROCESS_ASSET_METADATA_JOB_NAME,
    PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
    RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
    RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
    RUN_MANUAL_JOB_NAME,
    SCHEDULE_MANUAL_JOB_BATCH_NAME,
    clip_dedup_key,
    diagnostic_repair_dedup_key,
    diagnostic_run_dedup_key,
    dispatch_with_new_session,
    embedding_batch_dedup_key,
    faces_batch_dedup_key,
    faces_dedup_key,
    manual_batch_dedup_key,
    manual_run_dedup_key,
    metadata_dedup_key,
    preview_dedup_key,
    thumbnail_batch_dedup_key,
)


def _dispatch_succeeded(status: str) -> bool:
    return status in {"queued", "running"}


def resolve_default_model_id(task: str) -> int | None:
    with Session(engine) as session:
        try:
            return AIModelRepository(session).get_default_model_for_task(task).id
        except AIModelConfigurationError:
            return None


async def enqueue_asset_processing_job(
    asset_id: UUID,
    job_id: UUID | None = None,
    *,
    parent_job_id: UUID | None = None,
    enqueue_embedding: bool = True,
    enqueue_faces: bool = True,
    intent: str = INTENT_METADATA,
) -> bool:
    args: list[object] = [
        str(asset_id),
        None,
        str(parent_job_id) if parent_job_id is not None else None,
        enqueue_embedding,
        enqueue_faces,
    ]
    result = await dispatch_with_new_session(
        job_name=PROCESS_ASSET_METADATA_JOB_NAME,
        args=args,
        type=PROCESS_ASSET_METADATA_JOB_NAME,
        parameters={
            "asset_id": str(asset_id),
            "enqueue_embedding": enqueue_embedding,
            "enqueue_faces": enqueue_faces,
        },
        intent=intent,
        dedup_key=metadata_dedup_key(
            asset_id,
            enqueue_embedding=enqueue_embedding,
            enqueue_faces=enqueue_faces,
        ),
        related_asset_id=asset_id,
        parent_job_id=parent_job_id,
        is_visible=False,
        force=False,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_preview_job(
    asset_id: UUID,
    *,
    job_id: UUID | None = None,
    priority: str = "low",
    intent: str | None = None,
) -> bool:
    resolved_intent = intent or (INTENT_INTERACTIVE if priority == "high" else INTENT_PREVIEW)
    result = await dispatch_with_new_session(
        job_name=GENERATE_ASSET_PREVIEW_JOB_NAME,
        args=[str(asset_id), None, priority],
        type=GENERATE_ASSET_PREVIEW_JOB_NAME,
        parameters={"asset_id": str(asset_id), "priority": priority},
        intent=resolved_intent,
        dedup_key=preview_dedup_key(asset_id),
        related_asset_id=asset_id,
        is_visible=False,
        force=False,
        allow_active_duplicate=resolved_intent == INTENT_INTERACTIVE,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_embedding_job(
    asset_id: UUID,
    *,
    force: bool = False,
    job_id: UUID | None = None,
    intent: str = INTENT_AI,
) -> bool:
    model_id = resolve_default_model_id(AI_MODEL_TASK_CLIP_EMBEDDING)
    result = await dispatch_with_new_session(
        job_name=GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME,
        args=[str(asset_id), force, None],
        type=GENERATE_ASSET_CLIP_EMBEDDING_JOB_NAME,
        parameters={"asset_id": str(asset_id), "force": force},
        intent=intent,
        dedup_key=clip_dedup_key(asset_id, model_id=model_id),
        related_asset_id=asset_id,
        is_visible=False,
        force=force,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_faces_job(
    asset_id: UUID,
    *,
    force: bool = False,
    auto_match: bool = True,
    job_id: UUID | None = None,
    intent: str = INTENT_AI,
) -> bool:
    model_id = resolve_default_model_id(AI_MODEL_TASK_FACE_RECOGNITION)
    result = await dispatch_with_new_session(
        job_name=PROCESS_ASSET_FACES_JOB_NAME,
        args=[str(asset_id), force, auto_match, None],
        type=PROCESS_ASSET_FACES_JOB_NAME,
        parameters={
            "asset_id": str(asset_id),
            "force": force,
            "auto_match": auto_match,
        },
        intent=intent,
        dedup_key=faces_dedup_key(
            asset_id,
            model_id=model_id,
            auto_match=auto_match,
        ),
        related_asset_id=asset_id,
        is_visible=False,
        force=force,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_thumbnail_batch_job(
    items: list[dict[str, str | None]],
    *,
    intent: str = INTENT_BACKFILL,
) -> bool:
    asset_ids = [item["asset_id"] for item in items if item.get("asset_id")]
    result = await dispatch_with_new_session(
        job_name=PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
        args=[items],
        type=PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
        parameters={"asset_ids": asset_ids},
        intent=intent,
        dedup_key=thumbnail_batch_dedup_key(asset_ids=asset_ids),
        is_visible=False,
        force=False,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_embedding_batch_job(
    items: list[dict[str, str | None]],
    *,
    force: bool = False,
    intent: str = INTENT_AI,
) -> bool:
    asset_ids = [item["asset_id"] for item in items if item.get("asset_id")]
    result = await dispatch_with_new_session(
        job_name=GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
        args=[items, force],
        type=GENERATE_ASSET_CLIP_EMBEDDING_BATCH_JOB_NAME,
        parameters={"asset_ids": asset_ids, "force": force},
        intent=intent,
        dedup_key=embedding_batch_dedup_key(asset_ids=asset_ids, force=force),
        is_visible=False,
        force=force,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_asset_faces_batch_job(
    items: list[dict[str, str | None]],
    *,
    force: bool = False,
    auto_match: bool = True,
    intent: str = INTENT_AI,
) -> bool:
    asset_ids = [item["asset_id"] for item in items if item.get("asset_id")]
    result = await dispatch_with_new_session(
        job_name=PROCESS_ASSET_FACES_BATCH_JOB_NAME,
        args=[items, force, auto_match],
        type=PROCESS_ASSET_FACES_BATCH_JOB_NAME,
        parameters={
            "asset_ids": asset_ids,
            "force": force,
            "auto_match": auto_match,
        },
        intent=intent,
        dedup_key=faces_batch_dedup_key(
            asset_ids=asset_ids,
            force=force,
            auto_match=auto_match,
        ),
        is_visible=False,
        force=force,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_manual_job_run(
    job_id: UUID,
    *,
    job_key: str | None = None,
    intent: str = INTENT_MAINTENANCE,
) -> bool:
    result = await dispatch_with_new_session(
        job_name=RUN_MANUAL_JOB_NAME,
        args=[str(job_id)],
        type=RUN_MANUAL_JOB_NAME,
        parameters={"job_id": str(job_id), "job_key": job_key},
        intent=intent,
        dedup_key=manual_run_dedup_key(job_id, job_key=job_key),
        is_visible=True,
        force=False,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_system_integrity_diagnostic_run(
    *,
    diagnostic_key: str,
    run_id: UUID,
    job_id: UUID | None = None,
    intent: str = INTENT_MAINTENANCE,
) -> bool:
    result = await dispatch_with_new_session(
        job_name=RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
        args=[str(run_id)],
        type=RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
        parameters={"run_id": str(run_id), "diagnostic_key": diagnostic_key},
        intent=intent,
        dedup_key=diagnostic_run_dedup_key(diagnostic_key),
        job_key=f"diagnostic:{diagnostic_key}",
        is_visible=True,
        force=False,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_system_integrity_repair_run(
    *,
    diagnostic_run_id: UUID,
    repair_job_key: str,
    job_id: UUID | None = None,
    intent: str = INTENT_MAINTENANCE,
) -> bool:
    result = await dispatch_with_new_session(
        job_name=RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
        args=[str(diagnostic_run_id)],
        type=RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
        parameters={
            "diagnostic_run_id": str(diagnostic_run_id),
            "repair_job_key": repair_job_key,
        },
        intent=intent,
        dedup_key=diagnostic_repair_dedup_key(diagnostic_run_id),
        job_key=f"diagnostic:repair:{repair_job_key}",
        is_visible=True,
        force=False,
        existing_job_id=job_id,
    )
    return _dispatch_succeeded(result.job.status)


async def enqueue_manual_job_batch(
    parent_job_id: UUID,
    job_key: str,
    payload: dict[str, object],
    asset_ids: list[UUID],
    *,
    intent: str = INTENT_MAINTENANCE,
) -> bool:
    string_ids = [str(asset_id) for asset_id in asset_ids]
    result = await dispatch_with_new_session(
        job_name=SCHEDULE_MANUAL_JOB_BATCH_NAME,
        args=[str(parent_job_id), job_key, payload, string_ids],
        type=SCHEDULE_MANUAL_JOB_BATCH_NAME,
        parameters={
            "parent_job_id": str(parent_job_id),
            "job_key": job_key,
            "asset_ids": string_ids,
        },
        intent=intent,
        dedup_key=manual_batch_dedup_key(
            parent_job_id,
            job_key=job_key,
            asset_ids=string_ids,
        ),
        is_visible=False,
        force=False,
    )
    return _dispatch_succeeded(result.job.status)
