from __future__ import annotations

from app.services.embeddings.tasks import (
    generate_asset_clip_embedding as generate_asset_clip_embedding_job,
    generate_missing_asset_clip_embeddings as generate_missing_asset_clip_embeddings_job,
)
from app.services.faces.tasks import (
    generate_missing_asset_faces as generate_missing_asset_faces_job,
    process_asset_faces as process_asset_faces_job,
)
from app.services.people_clustering.tasks import (
    cluster_faces as cluster_faces_job,
)
from app.services.assets.jobs import (
    process_asset_metadata as process_asset_metadata_job,
)
from app.services.assets.scan import (
    scan_originals_library as scan_originals_library_job,
)


async def process_asset_metadata(
    ctx: dict[str, object], asset_id: str, job_id: str | None = None
) -> None:
    await process_asset_metadata_job(ctx, asset_id, job_id)


async def scan_originals_library(ctx: dict[str, object], job_id: str) -> dict[str, int]:
    return await scan_originals_library_job(ctx, job_id)


async def generate_asset_clip_embedding(
    ctx: dict[str, object],
    asset_id: str,
    force: bool = False,
    job_id: str | None = None,
) -> None:
    await generate_asset_clip_embedding_job(ctx, asset_id, force, job_id)


async def generate_missing_asset_clip_embeddings(
    ctx: dict[str, object],
    job_id: str,
    force: bool = False,
) -> dict[str, int]:
    return await generate_missing_asset_clip_embeddings_job(ctx, job_id, force)


async def process_asset_faces(
    ctx: dict[str, object],
    asset_id: str,
    force: bool = False,
    job_id: str | None = None,
) -> None:
    await process_asset_faces_job(ctx, asset_id, force, job_id)


async def generate_missing_asset_faces(
    ctx: dict[str, object],
    job_id: str,
    force: bool = False,
) -> dict[str, int]:
    return await generate_missing_asset_faces_job(ctx, job_id, force)


async def cluster_faces(
    ctx: dict[str, object],
    job_id: str,
    threshold: float,
    top_k: int,
    min_cluster_size: int,
) -> dict[str, int]:
    return await cluster_faces_job(
        ctx,
        job_id,
        threshold,
        top_k,
        min_cluster_size,
    )
