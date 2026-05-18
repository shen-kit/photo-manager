from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, create_engine

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://photo_manager:photo_manager@localhost:5432/photo_manager"
)
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
