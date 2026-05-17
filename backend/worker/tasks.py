from __future__ import annotations

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
