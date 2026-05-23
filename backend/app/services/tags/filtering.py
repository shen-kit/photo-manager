from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.models import AssetTag, Tag


def matching_assets_by_tag_filters_subquery(tag_ids: Sequence[int]):
    normalized = tuple(dict.fromkeys(tag_ids))
    if not normalized:
        return None
    selected_tag = aliased(Tag, name="selected_tag")
    assigned_tag = aliased(Tag, name="assigned_tag")
    return (
        select(AssetTag.asset_id.label("asset_id"))
        .select_from(AssetTag)
        .join(assigned_tag, assigned_tag.id == AssetTag.tag_id)
        .join(selected_tag, assigned_tag.path.op("<@")(selected_tag.path))
        .where(selected_tag.id.in_(normalized))
        .group_by(AssetTag.asset_id)
        .having(func.count(func.distinct(selected_tag.id)) == len(normalized))
        .subquery()
    )
