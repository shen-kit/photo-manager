from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models import User

router = APIRouter()


@router.get("/")
async def list_assets(current_user: User = Depends(get_current_user)) -> dict[str, list[dict[str, str]]]:
    return {"items": []}
