from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.v1.router import api_v1_router
from app.core.database import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Photo Manager API", lifespan=lifespan)
app.include_router(api_v1_router, prefix="/api/v1")


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
