from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.types import UserDefinedType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"


class Ltree(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "ltree"
