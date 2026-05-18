from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from app.services.embeddings.repository import (
    AssetEmbeddingSearchRow,
    EmbeddingRepository,
)
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError


@dataclass(frozen=True)
class SearchResults:
    query: str
    limit: int
    offset: int
    total: int
    items: list[AssetEmbeddingSearchRow]


class SearchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.embedding_service = EmbeddingService(session)
        self.embedding_repository = EmbeddingRepository(session)

    def search(self, *, query: str, limit: int, offset: int) -> SearchResults:
        normalized = query.strip()
        if not normalized:
            raise EmbeddingServiceError("Search query cannot be empty")
        model_id, query_embedding = self.embedding_service.embed_text_query(normalized)
        total = self.embedding_repository.count_searchable_assets(model_id=model_id)
        items = self.embedding_repository.search_similar_assets(
            model_id=model_id,
            query_embedding=query_embedding,
            limit=limit,
            offset=offset,
        )
        return SearchResults(
            query=normalized,
            limit=limit,
            offset=offset,
            total=total,
            items=items,
        )
