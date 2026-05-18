from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.models import Asset
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AIModelConfigurationError,
    AIModelRepository,
)
from app.services.assets.media import (
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
)
from app.services.embeddings.clip_model import (
    ClipEmbeddingError,
    embed_image,
    embed_text,
)
from app.services.embeddings.repository import EmbeddingRepository

logger = logging.getLogger(__name__)
SEARCH_DEFAULT_LIMIT = int(os.getenv("SEARCH_DEFAULT_LIMIT", "50"))
SEARCH_MAX_LIMIT = int(os.getenv("SEARCH_MAX_LIMIT", "100"))


class EmbeddingServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingGenerationResult:
    asset_id: UUID
    model_id: int
    generated: bool
    skipped: bool


class EmbeddingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = EmbeddingRepository(session)
        self.ai_model_repository = AIModelRepository(session)

    def generate_for_asset(
        self,
        asset_id: UUID,
        *,
        force: bool = False,
    ) -> EmbeddingGenerationResult:
        try:
            clip_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_CLIP_EMBEDDING
            )
        except AIModelConfigurationError as exc:
            raise EmbeddingServiceError(str(exc)) from exc
        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise EmbeddingServiceError(f"Asset {asset_id} not found")
        if asset.deleted_at is not None:
            raise EmbeddingServiceError(f"Asset {asset_id} is deleted")
        if not force and self.repository.asset_has_embedding(asset, clip_model.id):
            return EmbeddingGenerationResult(
                asset_id=asset.id,
                model_id=clip_model.id,
                generated=False,
                skipped=True,
            )

        source_path = self._resolve_embedding_source(asset)
        try:
            embedding = embed_image(
                source_path,
                model_name=clip_model.model_name,
                pretrained=clip_model.version_tag,
                expected_dimensions=clip_model.vector_dimensions,
            )
        except ClipEmbeddingError as exc:
            raise EmbeddingServiceError(str(exc)) from exc

        self.repository.upsert_asset_embedding(
            asset_id=asset.id,
            model_id=clip_model.id,
            embedding=embedding,
        )
        return EmbeddingGenerationResult(
            asset_id=asset.id,
            model_id=clip_model.id,
            generated=True,
            skipped=False,
        )

    def embed_text_query(self, query: str) -> tuple[int, list[float]]:
        normalized = query.strip()
        if not normalized:
            raise EmbeddingServiceError("Search query cannot be empty")
        try:
            clip_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_CLIP_EMBEDDING
            )
        except AIModelConfigurationError as exc:
            raise EmbeddingServiceError(str(exc)) from exc
        try:
            embedding = embed_text(
                normalized,
                model_name=clip_model.model_name,
                pretrained=clip_model.version_tag,
                expected_dimensions=clip_model.vector_dimensions,
            )
        except ClipEmbeddingError as exc:
            raise EmbeddingServiceError(str(exc)) from exc
        return clip_model.id, embedding

    def count_missing_embeddings(self, *, force: bool = False) -> tuple[int, int]:
        try:
            clip_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_CLIP_EMBEDDING
            )
        except AIModelConfigurationError as exc:
            raise EmbeddingServiceError(str(exc)) from exc
        total = self.repository.count_assets_missing_embeddings(
            model_id=clip_model.id,
            force=force,
        )
        return clip_model.id, total

    def list_missing_asset_ids(
        self,
        *,
        force: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[int, list[UUID]]:
        try:
            clip_model = self.ai_model_repository.get_default_model_for_task(
                AI_MODEL_TASK_CLIP_EMBEDDING
            )
        except AIModelConfigurationError as exc:
            raise EmbeddingServiceError(str(exc)) from exc
        asset_ids = self.repository.list_asset_ids_missing_embeddings(
            model_id=clip_model.id,
            force=force,
            limit=limit,
            offset=offset,
        )
        return clip_model.id, asset_ids

    def _resolve_embedding_source(self, asset: Asset) -> Path:
        if is_supported_video_mime_type(asset.mime_type):
            for name in ("small.webp", "tiny.webp"):
                preview_path = processed_asset_dir(asset.id) / name
                if preview_path.is_file():
                    return preview_path
            raise EmbeddingServiceError(
                f"No generated preview available for video asset {asset.id}"
            )

        try:
            source_path = master_path_to_source_path(asset.master_path)
        except ValueError as exc:
            raise EmbeddingServiceError(
                f"Invalid master path for asset {asset.id}"
            ) from exc
        if not source_path.is_file():
            raise EmbeddingServiceError(f"Source file missing for asset {asset.id}")
        return source_path
