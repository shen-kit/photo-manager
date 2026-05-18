"""add ai model defaults and registry metadata

Revision ID: 0004_ai_model_registry_defaults
Revises: 0003_asset_search_vector_hnsw
Create Date: 2026-05-18 00:00:03.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_ai_model_registry_defaults"
down_revision = "0003_asset_search_vector_hnsw"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_models", sa.Column("task", sa.Text(), nullable=True))
    op.add_column(
        "ai_models",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "ai_models",
        sa.Column(
            "is_deprecated",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        """
        UPDATE ai_models
        SET task = CASE
            WHEN model_name = 'openclip-vit-b-32' THEN 'clip_embedding'
            ELSE 'unknown'
        END
        WHERE task IS NULL
        """
    )
    op.execute("UPDATE ai_models SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE ai_models SET is_deprecated = false WHERE is_deprecated IS NULL")

    op.alter_column("ai_models", "task", nullable=False)
    op.alter_column("ai_models", "created_at", nullable=False)
    op.alter_column("ai_models", "is_deprecated", nullable=False)

    op.drop_constraint(
        "uq_ai_models_model_name_version_tag",
        "ai_models",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_models_task_model_name_version_tag",
        "ai_models",
        ["task", "model_name", "version_tag"],
    )

    op.create_table(
        "ai_model_defaults",
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["model_id"], ["ai_models.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("task"),
    )

    op.execute(
        """
        INSERT INTO ai_model_defaults (task, model_id)
        SELECT 'clip_embedding', id
        FROM ai_models
        WHERE task = 'clip_embedding'
          AND model_name = 'openclip-vit-b-32'
          AND version_tag = 'laion2b_s34b_b79k'
        ON CONFLICT (task)
        DO UPDATE SET model_id = EXCLUDED.model_id, updated_at = now()
        """
    )


def downgrade() -> None:
    op.drop_table("ai_model_defaults")

    op.drop_constraint(
        "uq_ai_models_task_model_name_version_tag",
        "ai_models",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_models_model_name_version_tag",
        "ai_models",
        ["model_name", "version_tag"],
    )

    op.drop_column("ai_models", "is_deprecated")
    op.drop_column("ai_models", "created_at")
    op.drop_column("ai_models", "task")
