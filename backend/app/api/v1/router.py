from fastapi import APIRouter

from app.api.v1.features.assets import router as assets_router


api_v1_router = APIRouter()
api_v1_router.include_router(assets_router, prefix="/assets", tags=["assets"])
