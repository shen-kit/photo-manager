"""add face recognition registry defaults and face schema fields

Revision ID: 0005_face_recognition_registry_and_faces_schema
Revises: 0004_ai_model_registry_defaults
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_face_recognition_registry_and_faces_schema"
down_revision = "0004_ai_model_registry_defaults"
branch_labels = None
depends_on = None


FACE_MODEL_NAME = "insightface-buffalo_l"
FACE_MODEL_VERSION = "buffalo_l"
FACE_MODEL_TASK = "face_recognition"
FACE_VECTOR_DIMENSIONS = 512


def upgrade() -> None:
    op.add_column("faces", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("faces", sa.Column("crop_path", sa.Text(), nullable=True))
    op.add_column(
        "faces",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "faces",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    op.execute("UPDATE faces SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE faces SET updated_at = now() WHERE updated_at IS NULL")

    op.alter_column("faces", "created_at", nullable=False)
    op.alter_column("faces", "updated_at", nullable=False)

    op.create_index("idx_faces_asset_id", "faces", ["asset_id"], unique=False)
    op.create_index("idx_faces_person_id", "faces", ["person_id"], unique=False)
    op.create_index("idx_faces_face_model_id", "faces", ["face_model_id"], unique=False)
    op.create_index(
        "idx_faces_embedding_hnsw",
        "faces",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL AND is_excluded = false"),
    )

    op.execute(
        sa.text(
            """
            WITH candidates AS (
                SELECT id, row_number() OVER (ORDER BY id) AS rn
                FROM ai_models
                WHERE model_name = :model_name
                  AND version_tag = :version_tag
            ),
            canonical AS (
                SELECT id FROM candidates WHERE rn = 1
            )
            UPDATE ai_models
            SET task = :task,
                vector_dimensions = :vector_dimensions,
                is_deprecated = false
            WHERE id = (SELECT id FROM canonical)
            """
        ).bindparams(
            model_name=FACE_MODEL_NAME,
            version_tag=FACE_MODEL_VERSION,
            task=FACE_MODEL_TASK,
            vector_dimensions=FACE_VECTOR_DIMENSIONS,
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO ai_models (
                task,
                model_name,
                version_tag,
                vector_dimensions,
                created_at,
                is_deprecated
            )
            SELECT :task, :model_name, :version_tag, :vector_dimensions, now(), false
            WHERE NOT EXISTS (
                SELECT 1
                FROM ai_models
                WHERE model_name = :model_name
                  AND version_tag = :version_tag
            )
            """
        ).bindparams(
            task=FACE_MODEL_TASK,
            model_name=FACE_MODEL_NAME,
            version_tag=FACE_MODEL_VERSION,
            vector_dimensions=FACE_VECTOR_DIMENSIONS,
        )
    )

    op.execute(
        sa.text(
            """
            WITH candidates AS (
                SELECT id, row_number() OVER (ORDER BY id) AS rn
                FROM ai_models
                WHERE model_name = :model_name
                  AND version_tag = :version_tag
            ),
            canonical AS (
                SELECT id FROM candidates WHERE rn = 1
            ),
            duplicates AS (
                SELECT id FROM candidates WHERE rn > 1
            )
            UPDATE faces
            SET face_model_id = (SELECT id FROM canonical)
            WHERE face_model_id IN (SELECT id FROM duplicates)
            """
        ).bindparams(model_name=FACE_MODEL_NAME, version_tag=FACE_MODEL_VERSION)
    )

    op.execute(
        sa.text(
            """
            WITH candidates AS (
                SELECT id, row_number() OVER (ORDER BY id) AS rn
                FROM ai_models
                WHERE model_name = :model_name
                  AND version_tag = :version_tag
            ),
            canonical AS (
                SELECT id FROM candidates WHERE rn = 1
            )
            INSERT INTO ai_model_defaults (task, model_id, updated_at)
            SELECT :task, id, now()
            FROM canonical
            ON CONFLICT (task)
            DO UPDATE SET model_id = EXCLUDED.model_id, updated_at = now()
            """
        ).bindparams(
            task=FACE_MODEL_TASK,
            model_name=FACE_MODEL_NAME,
            version_tag=FACE_MODEL_VERSION,
        )
    )

    op.execute(
        sa.text(
            """
            WITH candidates AS (
                SELECT id, row_number() OVER (ORDER BY id) AS rn
                FROM ai_models
                WHERE model_name = :model_name
                  AND version_tag = :version_tag
            ),
            duplicates AS (
                SELECT id FROM candidates WHERE rn > 1
            )
            DELETE FROM ai_models
            WHERE id IN (SELECT id FROM duplicates)
            """
        ).bindparams(model_name=FACE_MODEL_NAME, version_tag=FACE_MODEL_VERSION)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM ai_model_defaults WHERE task = :task").bindparams(
            task=FACE_MODEL_TASK
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE ai_models
            SET task = 'unknown'
            WHERE task = :task
              AND model_name = :model_name
              AND version_tag = :version_tag
            """
        ).bindparams(
            task=FACE_MODEL_TASK,
            model_name=FACE_MODEL_NAME,
            version_tag=FACE_MODEL_VERSION,
        )
    )

    op.drop_index("idx_faces_embedding_hnsw", table_name="faces", if_exists=True)
    op.drop_index("idx_faces_face_model_id", table_name="faces", if_exists=True)
    op.drop_index("idx_faces_person_id", table_name="faces", if_exists=True)
    op.drop_index("idx_faces_asset_id", table_name="faces", if_exists=True)

    op.drop_column("faces", "updated_at")
    op.drop_column("faces", "created_at")
    op.drop_column("faces", "crop_path")
    op.drop_column("faces", "confidence")
