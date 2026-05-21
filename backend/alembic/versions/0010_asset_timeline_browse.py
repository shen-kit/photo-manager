"""add asset timeline browse fields

Revision ID: 0010_asset_timeline_browse
Revises: 0009_asset_processing_generic
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_asset_timeline_browse"
down_revision = "0009_asset_processing_generic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("media_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("timeline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("timeline_day", sa.Date(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("timeline_month", sa.Date(), nullable=True),
    )

    op.execute(
        """
        UPDATE assets
        SET media_kind = CASE
                WHEN mime_type LIKE 'video/%' THEN 'video'
                ELSE 'image'
            END,
            timeline_at = COALESCE(captured_at, created_at, now()),
            timeline_day = COALESCE(
                CASE
                    WHEN captured_at_local ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN substring(captured_at_local from 1 for 10)::date
                    ELSE NULL
                END,
                COALESCE(captured_at, created_at, now())::date
            )
        """
    )
    op.execute(
        """
        UPDATE assets
        SET timeline_month = date_trunc('month', timeline_day)::date
        """
    )

    op.alter_column(
        "assets",
        "media_kind",
        nullable=False,
        server_default=sa.text("'image'"),
    )
    op.alter_column(
        "assets",
        "timeline_at",
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.alter_column(
        "assets",
        "timeline_day",
        nullable=False,
        server_default=sa.text("CURRENT_DATE"),
    )
    op.alter_column(
        "assets",
        "timeline_month",
        nullable=False,
        server_default=sa.text("date_trunc('month', CURRENT_DATE)::date"),
    )

    op.execute(
        """
        CREATE INDEX idx_assets_active_timeline_desc
        ON assets (timeline_at DESC, id DESC)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_assets_active_month_timeline_desc
        ON assets (timeline_month, timeline_at DESC, id DESC)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_assets_active_day_timeline_desc
        ON assets (timeline_day, timeline_at DESC, id DESC)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_assets_active_media_timeline_desc
        ON assets (media_kind, timeline_at DESC, id DESC)
        WHERE deleted_at IS NULL
        """
    )
    op.create_index(
        "idx_faces_person_asset_active",
        "faces",
        ["person_id", "asset_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_excluded = false AND person_id IS NOT NULL AND asset_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_faces_person_asset_active", table_name="faces", if_exists=True)
    op.drop_index(
        "idx_assets_active_media_timeline_desc",
        table_name="assets",
        if_exists=True,
    )
    op.drop_index(
        "idx_assets_active_day_timeline_desc",
        table_name="assets",
        if_exists=True,
    )
    op.drop_index(
        "idx_assets_active_month_timeline_desc",
        table_name="assets",
        if_exists=True,
    )
    op.drop_index(
        "idx_assets_active_timeline_desc",
        table_name="assets",
        if_exists=True,
    )
    op.drop_column("assets", "timeline_month")
    op.drop_column("assets", "timeline_day")
    op.drop_column("assets", "timeline_at")
    op.drop_column("assets", "media_kind")
