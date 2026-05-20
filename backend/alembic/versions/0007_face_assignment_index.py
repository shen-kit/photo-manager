"""add assigned face embedding index

Revision ID: 0007_face_assignment_index
Revises: 0006_people_thumbs
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007_face_assignment_index"
down_revision = "0006_people_thumbs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_faces_assigned_embedding_hnsw",
        "faces",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text(
            "embedding IS NOT NULL AND is_excluded = false AND person_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_faces_assigned_embedding_hnsw",
        table_name="faces",
        if_exists=True,
    )
