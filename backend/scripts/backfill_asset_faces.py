from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session

from app.core.database import engine
from app.services.manual_jobs.schemas import ManualJobRunRequest
from app.services.manual_jobs.service import ManualJobService


async def main() -> int:
    force = "--force" in sys.argv[1:]
    with Session(engine) as session:
        job = await ManualJobService(session).run_manual_job(
            job_key="run_missing_or_outdated_face_recognition",
            request=ManualJobRunRequest(params={"force": force, "auto_match": False}),
        )
        total = job.progress_total or 0
    print(f"Queued job {job.id} for {total} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
