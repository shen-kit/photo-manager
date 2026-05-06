from fastapi import APIRouter


router = APIRouter()


@router.get("/")
async def list_assets() -> dict[str, list[dict[str, str]]]:
    return {"items": []}
