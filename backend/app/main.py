from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.logging import setup_logging
from app.services.manual_jobs.api_executor import ApiManualJobExecutor

MEDIA_ORIGINALS_DIR = Path(os.getenv("MEDIA_ORIGINALS_DIR", "/media/originals"))
MEDIA_ORIGINALS_TMP_DIR = MEDIA_ORIGINALS_DIR / ".tmp"
MEDIA_PROCESSED_DIR = Path(os.getenv("MEDIA_PROCESSED_DIR", "/media/processed"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    MEDIA_ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_ORIGINALS_TMP_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stop_event = asyncio.Event()
    executor_task = asyncio.create_task(
        ApiManualJobExecutor().run_forever(stop_event=stop_event)
    )
    try:
        yield
    finally:
        stop_event.set()
        await executor_task


app = FastAPI(title="Photo Manager API", lifespan=lifespan)
app.include_router(api_v1_router, prefix="/api/v1")
app.mount(
    "/media/originals",
    StaticFiles(directory=MEDIA_ORIGINALS_DIR, check_dir=False),
    name="original-media",
)
app.mount(
    "/media/processed",
    StaticFiles(directory=MEDIA_PROCESSED_DIR, check_dir=False),
    name="processed-media",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/request")
async def debug_request(request: Request) -> dict[str, str | None]:
    return {
        "client_host": request.client.host if request.client else None,
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "x_forwarded_proto": request.headers.get("x-forwarded-proto"),
    }
