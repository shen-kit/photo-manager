"""extend tags for hierarchy albums

Revision ID: 0011_tag_hierarchy_albums
Revises: 0010_asset_timeline_browse
Create Date: 2026-05-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_tag_hierarchy_albums"
down_revision = "0010_asset_timeline_browse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("slug", sa.Text(), nullable=True))
    op.add_column(
        "tags",
        sa.Column(
            "is_album",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tags",
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tags",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "tags",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.execute(
        """
        UPDATE tags
        SET slug = subpath(path, nlevel(path) - 1, 1)::text,
            created_at = now(),
            updated_at = now()
        """
    )

    op.alter_column("tags", "slug", nullable=False)
    op.create_foreign_key(
        "fk_tags_cover_asset_id_assets",
        "tags",
        "assets",
        ["cover_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_tags_is_album", "tags", ["is_album"], unique=False)
    op.create_index("idx_tags_cover_asset_id", "tags", ["cover_asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_tags_cover_asset_id", table_name="tags", if_exists=True)
    op.drop_index("idx_tags_is_album", table_name="tags", if_exists=True)
    op.drop_constraint("fk_tags_cover_asset_id_assets", "tags", type_="foreignkey")
    op.drop_column("tags", "updated_at")
    op.drop_column("tags", "created_at")
    op.drop_column("tags", "cover_asset_id")
    op.drop_column("tags", "is_album")
    op.drop_column("tags", "slug")
