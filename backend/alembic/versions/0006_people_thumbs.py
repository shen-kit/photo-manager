"""add people thumbnail fields

Revision ID: 0006_people_thumbs
Revises: 0005_face_registry_schema
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_people_thumbs"
down_revision = "0005_face_registry_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("people", sa.Column("thumbnail_path", sa.Text(), nullable=True))
    op.add_column(
        "people",
        sa.Column(
            "thumbnail_manually_set",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("people", "thumbnail_manually_set")
    op.drop_column("people", "thumbnail_path")
