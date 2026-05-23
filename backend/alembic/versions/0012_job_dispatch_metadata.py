"""add job dispatch metadata

Revision ID: 0012_job_dispatch_metadata
Revises: 0011_tag_hierarchy_albums
Create Date: 2026-05-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_job_dispatch_metadata"
down_revision = "0011_tag_hierarchy_albums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("queue_name", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("intent", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("dedup_key", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("params_hash", sa.Text(), nullable=True))

    op.create_index(
        "idx_jobs_queue_name_status",
        "jobs",
        ["queue_name", "status"],
        unique=False,
    )
    op.create_index(
        "idx_jobs_dedup_key_status",
        "jobs",
        ["dedup_key", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_dedup_key_status", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_queue_name_status", table_name="jobs", if_exists=True)
    op.drop_column("jobs", "params_hash")
    op.drop_column("jobs", "dedup_key")
    op.drop_column("jobs", "intent")
    op.drop_column("jobs", "queue_name")
