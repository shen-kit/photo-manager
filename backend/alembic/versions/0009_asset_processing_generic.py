"""replace asset ai processing with generic asset processing

Revision ID: 0009_asset_processing_generic
Revises: 0008_manual_jobs_asset_ai
Create Date: 2026-05-21 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0009_asset_processing_generic"
down_revision = "0008_manual_jobs_asset_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS asset_ai_processing CASCADE")

    op.create_table(
        "asset_processing",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_model_id", sa.Integer(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "output_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ai_model_id"],
            ["ai_models.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["last_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_asset_processing_asset_task_null_model",
        "asset_processing",
        ["asset_id", "task"],
        unique=True,
        postgresql_where=sa.text("ai_model_id IS NULL"),
    )
    op.create_index(
        "uq_asset_processing_asset_model_task",
        "asset_processing",
        ["asset_id", "ai_model_id", "task"],
        unique=True,
        postgresql_where=sa.text("ai_model_id IS NOT NULL"),
    )
    op.create_index(
        "idx_asset_processing_task_model_status",
        "asset_processing",
        ["task", "ai_model_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_asset_processing_asset_task",
        "asset_processing",
        ["asset_id", "task"],
        unique=False,
    )
    op.create_index(
        "idx_asset_processing_last_job_id",
        "asset_processing",
        ["last_job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_asset_processing_last_job_id",
        table_name="asset_processing",
        if_exists=True,
    )
    op.drop_index(
        "idx_asset_processing_asset_task",
        table_name="asset_processing",
        if_exists=True,
    )
    op.drop_index(
        "idx_asset_processing_task_model_status",
        table_name="asset_processing",
        if_exists=True,
    )
    op.drop_index(
        "uq_asset_processing_asset_model_task",
        table_name="asset_processing",
        if_exists=True,
    )
    op.drop_index(
        "uq_asset_processing_asset_task_null_model",
        table_name="asset_processing",
        if_exists=True,
    )
    op.drop_table("asset_processing")

    op.create_table(
        "asset_ai_processing",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_model_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "output_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ai_model_id"],
            ["ai_models.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["last_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "ai_model_id",
            "task",
            name="uq_asset_ai_processing_asset_model_task",
        ),
    )
    op.create_index(
        "idx_asset_ai_processing_task_model_status",
        "asset_ai_processing",
        ["task", "ai_model_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_asset_ai_processing_asset_task",
        "asset_ai_processing",
        ["asset_id", "task"],
        unique=False,
    )
    op.create_index(
        "idx_asset_ai_processing_last_job_id",
        "asset_ai_processing",
        ["last_job_id"],
        unique=False,
    )
