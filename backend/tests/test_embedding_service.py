from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models import AIModel, Asset
from app.services.ai_models.repository import AI_MODEL_TASK_CLIP_EMBEDDING

sys.modules.setdefault("open_clip", SimpleNamespace())
sys.modules.setdefault(
    "torch",
    SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        nn=SimpleNamespace(Module=object),
        autocast=lambda *args, **kwargs: None,
        inference_mode=lambda: None,
        Tensor=object,
    ),
)

from app.services.embeddings.service import EmbeddingService


class _FakeAIModelRepository:
    def __init__(self, model: AIModel) -> None:
        self.model = model

    def get_default_model_for_task(self, task: str) -> AIModel:
        if task != AI_MODEL_TASK_CLIP_EMBEDDING:
            raise AssertionError(task)
        return self.model


class _FakeEmbeddingRepository:
    def __init__(self, *, asset: Asset, has_embedding: bool = False) -> None:
        self.asset = asset
        self.has_embedding = has_embedding
        self.upsert_calls: list[tuple] = []

    def get_asset(self, asset_id):
        return self.asset if asset_id == self.asset.id else None

    def asset_has_embedding(self, asset, model_id: int) -> bool:
        del asset, model_id
        return self.has_embedding

    def upsert_asset_embedding(self, *, asset_id, model_id, embedding):
        self.upsert_calls.append((asset_id, model_id, embedding))

    def count_assets_missing_embeddings(self, *, model_id: int, force: bool):
        del model_id, force
        return 0

    def list_asset_ids_missing_embeddings(
        self, *, model_id: int, force: bool, limit=None, offset=0
    ):
        del model_id, force, limit, offset
        return []


class _FakeAIProcessingRepository:
    def list_asset_ids_needing_clip_processing(
        self, *, ai_model_id: int, limit=None, offset=0
    ):
        del ai_model_id, limit, offset
        return []


class _FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.image_calls: list[tuple] = []
        self.text_calls: list[tuple] = []

    def embed_image(
        self,
        path: Path,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]:
        self.image_calls.append(
            (path, model_name, pretrained, expected_dimensions)
        )
        return [0.1, 0.2, 0.3]

    def embed_text(
        self,
        query: str,
        *,
        model_name: str,
        pretrained: str,
        expected_dimensions: int | None,
    ) -> list[float]:
        self.text_calls.append(
            (query, model_name, pretrained, expected_dimensions)
        )
        return [0.4, 0.5]


class EmbeddingServiceTest(unittest.TestCase):
    def _asset(self, path: Path, *, mime_type: str = "image/jpeg") -> Asset:
        return Asset(
            id=uuid4(),
            file_hash="hash",
            master_path=path.name,
            mime_type=mime_type,
            has_large_preview=False,
            created_at=datetime.now(timezone.utc),
        )

    def _model(self, model_id: int = 11) -> AIModel:
        return AIModel(
            id=model_id,
            task=AI_MODEL_TASK_CLIP_EMBEDDING,
            model_name="ViT-B-32",
            version_tag="laion2b_s34b_b79k",
            vector_dimensions=512,
            is_deprecated=False,
        )

    def test_generate_for_asset_uses_injected_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "photo.jpg"
            image_path.write_bytes(b"stub")
            asset = self._asset(image_path)
            repository = _FakeEmbeddingRepository(asset=asset)
            provider = _FakeEmbeddingProvider()
            service = EmbeddingService(
                session=None,
                repository=repository,
                ai_processing_repository=_FakeAIProcessingRepository(),
                ai_model_repository=_FakeAIModelRepository(self._model()),
                provider=provider,
            )

            from unittest.mock import patch

            with patch(
                "app.services.embeddings.service.master_path_to_source_path",
                return_value=image_path,
            ):
                result = service.generate_for_asset(asset.id)

        self.assertTrue(result.generated)
        self.assertFalse(result.skipped)
        self.assertEqual(len(provider.image_calls), 1)
        self.assertEqual(provider.image_calls[0][0], image_path)
        self.assertEqual(
            repository.upsert_calls,
            [(asset.id, 11, [0.1, 0.2, 0.3])],
        )

    def test_embed_text_query_uses_injected_provider(self) -> None:
        provider = _FakeEmbeddingProvider()
        service = EmbeddingService(
            session=None,
            repository=_FakeEmbeddingRepository(
                asset=Asset(
                    id=uuid4(),
                    file_hash="hash",
                    master_path="2026/05/photo.jpg",
                    mime_type="image/jpeg",
                    has_large_preview=False,
                    created_at=datetime.now(timezone.utc),
                )
            ),
            ai_processing_repository=_FakeAIProcessingRepository(),
            ai_model_repository=_FakeAIModelRepository(self._model(model_id=21)),
            provider=provider,
        )

        model_id, embedding = service.embed_text_query(" beach ")

        self.assertEqual(model_id, 21)
        self.assertEqual(embedding, [0.4, 0.5])
        self.assertEqual(
            provider.text_calls,
            [("beach", "ViT-B-32", "laion2b_s34b_b79k", 512)],
        )


if __name__ == "__main__":
    unittest.main()
