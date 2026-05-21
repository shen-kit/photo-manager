from fastapi import APIRouter

from app.api.v1.features.auth import router as auth_router
from app.api.v1.features.assets import router as assets_router
from app.api.v1.features.faces import router as faces_router
from app.api.v1.features.jobs import router as jobs_router
from app.api.v1.features.notifications import router as notifications_router
from app.api.v1.features.people import router as people_router
from app.api.v1.features.search import router as search_router
from app.api.v1.features.timeline import router as timeline_router
from app.api.v1.features.trash import router as trash_router


api_v1_router = APIRouter()
api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(assets_router, prefix="/assets", tags=["assets"])
api_v1_router.include_router(faces_router, tags=["faces"])
api_v1_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_v1_router.include_router(
    notifications_router, prefix="/notifications", tags=["notifications"]
)
api_v1_router.include_router(people_router, tags=["people"])
api_v1_router.include_router(search_router, prefix="/search", tags=["search"])
api_v1_router.include_router(timeline_router, tags=["timeline"])
api_v1_router.include_router(trash_router, prefix="/trash", tags=["trash"])
