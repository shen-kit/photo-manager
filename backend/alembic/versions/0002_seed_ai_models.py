"""seed ai models

Revision ID: 0002_seed_ai_models
Revises: 0001_initial
Create Date: 2026-05-18 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

# revision identifiers, used by Alembic.
revision = "0002_seed_ai_models"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


AI_MODELS = (
    {
        "model_name": "openclip-vit-b-32",
        "version_tag": "laion2b_s34b_b79k",
        "vector_dimensions": 512,
    },
    {
        "model_name": "insightface-buffalo_l",
        "version_tag": "buffalo_l",
        "vector_dimensions": 512,
    },
)


def upgrade() -> None:
    ai_models = sa.table(
        "ai_models",
        sa.column("model_name", sa.Text()),
        sa.column("version_tag", sa.Text()),
        sa.column("vector_dimensions", sa.Integer()),
    )

    statement = insert(ai_models).values(AI_MODELS)
    statement = statement.on_conflict_do_update(
        constraint="uq_ai_models_model_name_version_tag",
        set_={
            "vector_dimensions": statement.excluded.vector_dimensions,
        },
    )
    op.execute(statement)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM ai_models
            WHERE (model_name, version_tag) IN (
                ('openclip-vit-b-32', 'laion2b_s34b_b79k'),
                ('insightface-buffalo_l', 'buffalo_l')
            )
            """
        )
    )
