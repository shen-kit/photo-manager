"""add asset search vector hnsw index

Revision ID: 0003_asset_search_vector_hnsw
Revises: 0002_seed_ai_models
Create Date: 2026-05-18 00:00:02.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_asset_search_vector_hnsw"
down_revision = "0002_seed_ai_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_assets_search_vector_hnsw",
        "assets",
        ["search_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"search_vector": "vector_cosine_ops"},
        postgresql_where=sa.text("search_vector IS NOT NULL"),
    )
    op.create_index(
        "idx_assets_search_model_id",
        "assets",
        ["search_model_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_assets_search_model_id", table_name="assets", if_exists=True)
    op.drop_index(
        "idx_assets_search_vector_hnsw",
        table_name="assets",
        if_exists=True,
    )
