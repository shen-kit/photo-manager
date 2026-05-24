"""add system integrity diagnostics

Revision ID: 0013_integrity_diag
Revises: 0012_job_dispatch_metadata
Create Date: 2026-05-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_integrity_diag"
down_revision = "0012_job_dispatch_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("diagnostic_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("health_state", sa.Text(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "sample_items_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("repair_job_key", sa.Text(), nullable=True),
        sa.Column("related_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "latest_repair_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["latest_repair_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_diagnostic_runs_key_checked_at",
        "diagnostic_runs",
        ["diagnostic_key", sa.text("checked_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_runs_key_created_at",
        "diagnostic_runs",
        ["diagnostic_key", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_runs_status",
        "diagnostic_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_runs_related_job_id",
        "diagnostic_runs",
        ["related_job_id"],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_runs_latest_repair_job_id",
        "diagnostic_runs",
        ["latest_repair_job_id"],
        unique=False,
    )

    op.create_table(
        "diagnostic_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("diagnostic_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relative_path", sa.Text(), nullable=True),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column(
            "repairable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["diagnostic_run_id"], ["diagnostic_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_diagnostic_run_items_run_id_id",
        "diagnostic_run_items",
        ["diagnostic_run_id", "id"],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_run_items_asset_id",
        "diagnostic_run_items",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_run_items_person_id",
        "diagnostic_run_items",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "idx_diagnostic_run_items_reason_code",
        "diagnostic_run_items",
        ["reason_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_diagnostic_run_items_reason_code",
        table_name="diagnostic_run_items",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_run_items_person_id",
        table_name="diagnostic_run_items",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_run_items_asset_id",
        table_name="diagnostic_run_items",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_run_items_run_id_id",
        table_name="diagnostic_run_items",
        if_exists=True,
    )
    op.drop_table("diagnostic_run_items")

    op.drop_index(
        "idx_diagnostic_runs_latest_repair_job_id",
        table_name="diagnostic_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_runs_related_job_id",
        table_name="diagnostic_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_runs_status",
        table_name="diagnostic_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_runs_key_created_at",
        table_name="diagnostic_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_diagnostic_runs_key_checked_at",
        table_name="diagnostic_runs",
        if_exists=True,
    )
    op.drop_table("diagnostic_runs")
