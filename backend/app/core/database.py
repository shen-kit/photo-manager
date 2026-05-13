from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://photo_manager:photo_manager@localhost:5432/photo_manager"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


SCHEMA_PATCHES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS description TEXT', ("assets",)),
    ("ALTER TABLE assets ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN NOT NULL DEFAULT false", ("assets",)),
    ("ALTER TABLE assets ADD COLUMN IF NOT EXISTS has_large_preview BOOLEAN NOT NULL DEFAULT false", ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS captured_at_local TEXT', ("assets", "ai_models")),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS video_codec TEXT', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS audio_codec TEXT', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS duration_seconds DOUBLE PRECISION', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS preview_status TEXT', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS exif_data JSONB', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS search_vector vector(512)', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS search_model_id INTEGER REFERENCES ai_models(id)', ("assets", "ai_models")),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS blurhash TEXT', ("assets",)),
    ('ALTER TABLE assets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ', ("assets",)),
    ('ALTER TABLE people ADD COLUMN IF NOT EXISTS thumbnail_face_id UUID REFERENCES faces(id)', ("people", "faces")),
    ("ALTER TABLE people ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT false", ("people",)),
    ('ALTER TABLE faces ADD COLUMN IF NOT EXISTS bounding_box JSONB', ("faces",)),
    ('ALTER TABLE faces ADD COLUMN IF NOT EXISTS embedding vector(512)', ("faces",)),
    ('ALTER TABLE faces ADD COLUMN IF NOT EXISTS face_model_id INTEGER REFERENCES ai_models(id)', ("faces", "ai_models")),
    ("ALTER TABLE faces ADD COLUMN IF NOT EXISTS is_confirmed BOOLEAN NOT NULL DEFAULT false", ("faces",)),
    ("ALTER TABLE faces ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT false", ("faces",)),
    ('ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ', ("refresh_tokens",)),
    ('ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS replaced_by_token_id UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL', ("refresh_tokens",)),
    ("CREATE INDEX IF NOT EXISTS idx_assets_captured_at ON assets (captured_at DESC)", ("assets",)),
    ("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens (user_id)", ("refresh_tokens",)),
    ("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens (expires_at)", ("refresh_tokens",)),
    ("CREATE INDEX IF NOT EXISTS idx_tags_path_gist ON tags USING gist (path)", ("tags",)),
)


def _table_exists(connection, table_name: str) -> bool:
    result = connection.exec_driver_sql(f"SELECT to_regclass('public.{table_name}')")
    return result.scalar_one() is not None


def _apply_schema_patches(connection) -> None:
    for statement, dependencies in SCHEMA_PATCHES:
        if any(not _table_exists(connection, dependency) for dependency in dependencies):
            continue
        connection.exec_driver_sql(statement)


def create_db_and_tables() -> None:
    # Import models so SQLModel metadata is fully populated before create_all.
    from app import models  # noqa: F401

    with engine.begin() as connection:
        # pgvector exposes the `vector` extension name in PostgreSQL.
        connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "vector";')
        connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "ltree";')
        SQLModel.metadata.create_all(connection)
        _apply_schema_patches(connection)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
