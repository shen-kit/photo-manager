from __future__ import annotations

from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_image(
        self,
        path: Path,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]: ...

    def embed_text(
        self,
        query: str,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]: ...


class OpenClipEmbeddingProvider:
    def embed_image(
        self,
        path: Path,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]:
        from app.services.embeddings.clip_model import embed_image

        return embed_image(
            path,
            model_name=model_name,
            pretrained=pretrained,
            expected_dimensions=expected_dimensions,
        )

    def embed_text(
        self,
        query: str,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]:
        from app.services.embeddings.clip_model import embed_text

        return embed_text(
            query,
            model_name=model_name,
            pretrained=pretrained,
            expected_dimensions=expected_dimensions,
        )
