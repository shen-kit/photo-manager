from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session

from app.core.database import engine
from app.services.faces.tasks import create_backfill_job
from app.services.jobs.queue import enqueue_missing_asset_faces_job
from app.services.jobs.service import JobService


async def main() -> int:
    force = "--force" in sys.argv[1:]
    job_id, total = create_backfill_job(force=force)
    queued = await enqueue_missing_asset_faces_job(job_id, force=force)
    if not queued:
        with Session(engine) as session:
            JobService(session).fail_job(job_id, "Failed to enqueue face backfill job")
        print(f"Failed to enqueue job {job_id}")
        return 1
    print(f"Queued job {job_id} for {total} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
