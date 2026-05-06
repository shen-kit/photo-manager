from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://photo_manager:photo_manager@localhost:5432/photo_manager"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_db_and_tables() -> None:
    # Import models so SQLModel metadata is fully populated before create_all.
    from app import models  # noqa: F401

    with engine.begin() as connection:
        # pgvector exposes the `vector` extension name in PostgreSQL.
        connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "vector";')
        connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "ltree";')
        SQLModel.metadata.create_all(connection)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
