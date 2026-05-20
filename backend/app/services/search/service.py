from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.services.embeddings.repository import (
    AssetEmbeddingSearchRow,
    EmbeddingRepository,
)
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError
from app.services.people.service import PeopleService


@dataclass(frozen=True)
class SearchResults:
    query: str
    limit: int
    offset: int
    total: int
    items: list[AssetEmbeddingSearchRow]


class SearchService:
    def __init__(
        self,
        session: Session,
        *,
        embedding_service: EmbeddingService | None = None,
        embedding_repository: EmbeddingRepository | None = None,
        people_service: PeopleService | None = None,
    ) -> None:
        self.session = session
        self.embedding_service = embedding_service or EmbeddingService(session)
        self.embedding_repository = embedding_repository or EmbeddingRepository(session)
        self.people_service = people_service or PeopleService(session)

    def search(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        person_ids: list[UUID] | None = None,
    ) -> SearchResults:
        normalized = query.strip() if query else ""
        validated_person_ids = self.people_service.validate_person_ids(person_ids or [])
        if not normalized and not validated_person_ids:
            raise EmbeddingServiceError(
                "Search query or person_ids filter must be provided"
            )

        if normalized:
            model_id, query_embedding = self.embedding_service.embed_text_query(
                normalized
            )
            total = self.embedding_repository.count_searchable_assets(
                model_id=model_id,
                person_ids=validated_person_ids,
            )
            items = self.embedding_repository.search_similar_assets(
                model_id=model_id,
                query_embedding=query_embedding,
                limit=limit,
                offset=offset,
                person_ids=validated_person_ids,
            )
        else:
            total = self.embedding_repository.count_assets_for_people(
                person_ids=validated_person_ids
            )
            items = self.embedding_repository.list_assets_for_people(
                person_ids=validated_person_ids,
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
