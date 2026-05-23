from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlmodel import SQLModel

from app.api.v1.features.assets.router import (
    AssetGridPageResponse,
    _build_grid_item,
    _parse_person_ids,
)
from app.api.v1.features.tags import _tag_response
from app.core.auth import get_current_user
from app.models import User
from app.services.assets.browse import (
    DEFAULT_GRID_LIMIT,
    AssetBrowseService,
    AssetGridFilters,
    get_asset_browse_service,
)
from app.services.people.service import PeopleService, get_people_service
from app.services.tags.schemas import TagNode
from app.services.tags.service import TagService, get_tag_service

router = APIRouter()


class AlbumCreateRequest(SQLModel):
    name: str
    parent_id: int | None = None
    description: str | None = None
    cover_asset_id: UUID | None = None


class AlbumUpdateRequest(SQLModel):
    name: str | None = None
    parent_id: int | None = None
    description: str | None = None
    cover_asset_id: UUID | None = None


@router.get("", response_model=list[TagNode], include_in_schema=False)
@router.get("/", response_model=list[TagNode])
def list_albums(
    parent_id: int | None = Query(default=None),
    subtree_id: int | None = Query(default=None),
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> list[TagNode]:
    del current_user
    return [
        _tag_response(tag)
        for tag in tag_service.list_tags(
            is_album=True,
            parent_id=parent_id,
            subtree_id=subtree_id,
        )
    ]


@router.post("/", response_model=TagNode, status_code=status.HTTP_201_CREATED)
def create_album(
    payload: AlbumCreateRequest,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> TagNode:
    del current_user
    tag = tag_service.create_tag(
        name=payload.name,
        parent_id=payload.parent_id,
        description=payload.description,
        cover_asset_id=payload.cover_asset_id,
        is_album=True,
    )
    return _tag_response(tag)


@router.get("/{album_id}", response_model=TagNode)
def get_album(
    album_id: int,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> TagNode:
    del current_user
    return _tag_response(tag_service.get_tag(album_id, is_album=True))


@router.patch("/{album_id}", response_model=TagNode)
def update_album(
    album_id: int,
    payload: AlbumUpdateRequest,
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> TagNode:
    del current_user
    updates = payload.model_dump(exclude_unset=True)
    album = tag_service.update_tag(
        album_id,
        is_album=True,
        name=updates.get("name"),
        parent_id=updates.get("parent_id"),
        set_parent="parent_id" in updates,
        description=updates.get("description"),
        clear_description="description" in updates
        and updates.get("description") is None,
        cover_asset_id=updates.get("cover_asset_id"),
        clear_cover="cover_asset_id" in updates
        and updates.get("cover_asset_id") is None,
    )
    return _tag_response(album)


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(
    album_id: int,
    delete_children: bool = Query(default=False),
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    del current_user
    tag_service.delete_tag(album_id, is_album=True, delete_children=delete_children)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{album_id}/assets", response_model=AssetGridPageResponse)
def list_album_assets(
    album_id: int,
    request: Request,
    limit: int = Query(default=DEFAULT_GRID_LIMIT, ge=1, le=200),
    cursor: str | None = Query(default=None),
    media_kind: str | None = Query(default=None),
    month: date | None = Query(default=None),
    day: date | None = Query(default=None),
    person_ids: str | None = Query(default=None),
    browse_service: AssetBrowseService = Depends(get_asset_browse_service),
    people_service: PeopleService = Depends(get_people_service),
    tag_service: TagService = Depends(get_tag_service),
    current_user: User = Depends(get_current_user),
) -> AssetGridPageResponse:
    del current_user
    tag_service.get_tag(album_id, is_album=True)
    filters = AssetGridFilters(
        media_kind=media_kind,
        month=month,
        day=day,
        person_ids=tuple(
            people_service.validate_person_ids(list(_parse_person_ids(person_ids)))
        ),
        tag_ids=(album_id,),
    )
    page = browse_service.list_asset_grid_page(
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    return AssetGridPageResponse(
        items=[_build_grid_item(request, row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )
