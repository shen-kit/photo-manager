"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app import models as app_models

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "ltree"')

    op.create_table(
        "ai_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("version_tag", sa.Text(), nullable=False),
        sa.Column("vector_dimensions", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_name",
            "version_tag",
            name="uq_ai_models_model_name_version_tag",
        ),
    )

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("master_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at_local", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_favorite",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "has_large_preview",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("video_codec", sa.Text(), nullable=True),
        sa.Column("audio_codec", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("preview_status", sa.Text(), nullable=True),
        sa.Column("exif_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("search_vector", app_models.Vector(512), nullable=True),
        sa.Column("search_model_id", sa.Integer(), nullable=True),
        sa.Column("blurhash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["search_model_id"], ["ai_models.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash"),
    )

    op.create_index(
        "idx_assets_captured_at",
        "assets",
        [sa.text("captured_at DESC")],
        unique=False,
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "progress_current",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_message", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_jobs_created_at", "jobs", [sa.text("created_at DESC")], unique=False
    )
    op.create_index("idx_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("idx_jobs_type", "jobs", ["type"], unique=False)

    op.create_table(
        "people",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("thumbnail_face_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", app_models.Ltree(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )
    op.create_index(
        "idx_tags_path_gist",
        "tags",
        ["path"],
        unique=False,
        postgresql_using="gist",
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "faces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "bounding_box",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("embedding", app_models.Vector(512), nullable=True),
        sa.Column("face_model_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_confirmed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_excluded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["face_model_id"], ["ai_models.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "fk_people_thumbnail_face_id_faces",
        "people",
        "faces",
        ["thumbnail_face_id"],
        ["id"],
    )

    op.create_table(
        "asset_tags",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "tag_id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("related_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["related_asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["related_job_id"],
            ["jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifications_category", "notifications", ["category"], unique=False
    )
    op.create_index(
        "idx_notifications_created_at",
        "notifications",
        [sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index("idx_notifications_level", "notifications", ["level"], unique=False)
    op.create_index(
        "idx_notifications_read_at", "notifications", ["read_at"], unique=False
    )
    op.create_index(
        "idx_notifications_related_job_id",
        "notifications",
        ["related_job_id"],
        unique=False,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(
        "idx_refresh_tokens_user_id", table_name="refresh_tokens", if_exists=True
    )
    op.drop_index(
        "idx_refresh_tokens_expires_at",
        table_name="refresh_tokens",
        if_exists=True,
    )
    op.drop_table("refresh_tokens", if_exists=True)

    op.drop_index(
        "idx_notifications_related_job_id",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_index(
        "idx_notifications_read_at", table_name="notifications", if_exists=True
    )
    op.drop_index("idx_notifications_level", table_name="notifications", if_exists=True)
    op.drop_index(
        "idx_notifications_created_at",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_index(
        "idx_notifications_category",
        table_name="notifications",
        if_exists=True,
    )
    op.drop_table("notifications", if_exists=True)

    op.drop_table("asset_tags", if_exists=True)

    op.drop_constraint(
        "fk_people_thumbnail_face_id_faces",
        "people",
        type_="foreignkey",
    )
    op.drop_table("faces", if_exists=True)
    op.drop_table("users", if_exists=True)

    op.drop_index("idx_tags_path_gist", table_name="tags", if_exists=True)
    op.drop_table("tags", if_exists=True)

    op.drop_table("people", if_exists=True)

    op.drop_index("idx_jobs_type", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_status", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_created_at", table_name="jobs", if_exists=True)
    op.drop_table("jobs", if_exists=True)

    op.drop_index("idx_assets_captured_at", table_name="assets", if_exists=True)
    op.drop_table("assets", if_exists=True)

    op.drop_table("ai_models", if_exists=True)
