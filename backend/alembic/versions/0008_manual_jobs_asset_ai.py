"""add manual job tracking and asset ai processing

Revision ID: 0008_manual_jobs_asset_ai_processing
Revises: 0007_face_assignment_index
Create Date: 2026-05-20 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_manual_jobs_asset_ai"
down_revision = "0007_face_assignment_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("job_key", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("parent_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("related_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "is_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_foreign_key(
        "fk_jobs_parent_job_id_jobs",
        "jobs",
        "jobs",
        ["parent_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_jobs_related_asset_id_assets",
        "jobs",
        "assets",
        ["related_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_jobs_job_key_status",
        "jobs",
        ["job_key", "status"],
        unique=False,
    )
    op.create_index(
        "idx_jobs_parent_job_id_created_at",
        "jobs",
        [sa.text("parent_job_id"), sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_jobs_related_asset_id",
        "jobs",
        ["related_asset_id"],
        unique=False,
    )
    op.create_index(
        "uq_jobs_parent_related_asset",
        "jobs",
        ["parent_job_id", "related_asset_id"],
        unique=True,
        postgresql_where=sa.text(
            "parent_job_id IS NOT NULL AND related_asset_id IS NOT NULL"
        ),
    )

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


def downgrade() -> None:
    op.drop_index(
        "idx_asset_ai_processing_last_job_id",
        table_name="asset_ai_processing",
        if_exists=True,
    )
    op.drop_index(
        "idx_asset_ai_processing_asset_task",
        table_name="asset_ai_processing",
        if_exists=True,
    )
    op.drop_index(
        "idx_asset_ai_processing_task_model_status",
        table_name="asset_ai_processing",
        if_exists=True,
    )
    op.drop_table("asset_ai_processing")

    op.drop_index("uq_jobs_parent_related_asset", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_related_asset_id", table_name="jobs", if_exists=True)
    op.drop_index(
        "idx_jobs_parent_job_id_created_at", table_name="jobs", if_exists=True
    )
    op.drop_index("idx_jobs_job_key_status", table_name="jobs", if_exists=True)
    op.drop_constraint("fk_jobs_related_asset_id_assets", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_parent_job_id_jobs", "jobs", type_="foreignkey")
    op.drop_column("jobs", "is_visible")
    op.drop_column("jobs", "related_asset_id")
    op.drop_column("jobs", "parent_job_id")
    op.drop_column("jobs", "job_key")
