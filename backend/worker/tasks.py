from __future__ import annotations

from uuid import UUID

from app.services.embeddings.tasks import (
    generate_asset_clip_embedding as generate_asset_clip_embedding_job,
)
from app.services.embeddings.tasks import (
    generate_asset_clip_embedding_batch as generate_asset_clip_embedding_batch_job,
)
from app.services.faces.tasks import (
    process_asset_faces as process_asset_faces_job,
)
from app.services.faces.tasks import (
    process_asset_faces_batch as process_asset_faces_batch_job,
)
from app.services.assets.jobs import (
    process_asset_metadata as process_asset_metadata_job,
)
from app.services.assets.jobs import (
    generate_asset_preview as generate_asset_preview_job,
)
from app.services.assets.jobs import (
    process_asset_thumbnail_batch as process_asset_thumbnail_batch_job,
)
from app.services.manual_jobs.service import ManualJobService
from app.core.database import engine
from sqlmodel import Session


def _notify_manual_job_child_terminal(job_id: str | None) -> None:
    if job_id is None:
        return
    with Session(engine) as session:
        ManualJobService(session).on_child_job_terminal(UUID(job_id))


async def process_asset_metadata(
    ctx: dict[str, object],
    asset_id: str,
    job_id: str | None = None,
    parent_job_id: str | None = None,
    enqueue_embedding: bool = True,
    enqueue_faces: bool = True,
) -> None:
    try:
        await process_asset_metadata_job(
            ctx,
            asset_id,
            job_id,
            parent_job_id,
            enqueue_embedding,
            enqueue_faces,
        )
    finally:
        _notify_manual_job_child_terminal(job_id)


async def generate_asset_clip_embedding(
    ctx: dict[str, object],
    asset_id: str,
    force: bool = False,
    job_id: str | None = None,
) -> None:
    try:
        await generate_asset_clip_embedding_job(ctx, asset_id, force, job_id)
    finally:
        _notify_manual_job_child_terminal(job_id)


async def generate_asset_clip_embedding_batch(
    ctx: dict[str, object],
    items: list[dict[str, str | None]],
    force: bool = False,
) -> None:
    try:
        await generate_asset_clip_embedding_batch_job(ctx, items, force)
    finally:
        for item in items:
            _notify_manual_job_child_terminal(item.get("job_id"))


async def process_asset_faces(
    ctx: dict[str, object],
    asset_id: str,
    force: bool = False,
    auto_match: bool = True,
    job_id: str | None = None,
) -> None:
    try:
        await process_asset_faces_job(ctx, asset_id, force, auto_match, job_id)
    finally:
        _notify_manual_job_child_terminal(job_id)


async def process_asset_faces_batch(
    ctx: dict[str, object],
    items: list[dict[str, str | None]],
    force: bool = False,
    auto_match: bool = True,
) -> None:
    try:
        await process_asset_faces_batch_job(ctx, items, force, auto_match)
    finally:
        for item in items:
            _notify_manual_job_child_terminal(item.get("job_id"))


async def process_asset_thumbnail_batch(
    ctx: dict[str, object],
    items: list[dict[str, str | None]],
) -> None:
    try:
        await process_asset_thumbnail_batch_job(ctx, items)
    finally:
        for item in items:
            _notify_manual_job_child_terminal(item.get("job_id"))


async def generate_asset_preview(
    ctx: dict[str, object],
    asset_id: str,
    job_id: str | None = None,
    priority: str = "low",
) -> None:
    try:
        await generate_asset_preview_job(ctx, asset_id, job_id, priority)
    finally:
        _notify_manual_job_child_terminal(job_id)


async def run_manual_job(
    _: dict[str, object],
    job_id: str,
) -> None:
    with Session(engine) as session:
        await ManualJobService(session).execute_parent_job(job_id=UUID(job_id))


async def schedule_manual_job_batch(
    _: dict[str, object],
    parent_job_id: str,
    job_key: str,
    payload: dict[str, object],
    asset_ids: list[str],
) -> None:
    with Session(engine) as session:
        await ManualJobService(session).execute_batch(
            parent_job_id=UUID(parent_job_id),
            job_key=job_key,
            payload=payload,
            asset_ids=[UUID(asset_id) for asset_id in asset_ids],
        )
