from __future__ import annotations

import hashlib
from pathlib import Path

HASH_CHUNK_SIZE = 1024 * 1024


def compute_sha256(path: Path, *, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
