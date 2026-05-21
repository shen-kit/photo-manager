from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.models import Asset
from app.services.assets.media import (
    is_supported_image_mime_type,
    is_supported_video_mime_type,
    master_path_to_source_path,
    processed_asset_dir,
    should_generate_small_in_api,
    write_asset_variants,
)
from app.services.embeddings.service import EmbeddingService
from app.services.faces.service import FaceProcessingService


@dataclass(frozen=True)
class BatchProcessingItem:
    asset_id: UUID
    job_id: UUID | None = None


class ThumbnailBatchProcessor:
    def __init__(self, session: Session) -> None:
        self.session = session

    def process_batch(
        self, items: list[BatchProcessingItem]
    ) -> dict[UUID, Exception | None]:
        results: dict[UUID, Exception | None] = {}
        for item in items:
            try:
                self.ensure_asset_thumbnails(item.asset_id)
            except Exception as exc:
                results[item.asset_id] = exc
            else:
                results[item.asset_id] = None
        return results

    def ensure_asset_thumbnails(self, asset_id: UUID) -> None:
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            return
        if not (
            is_supported_image_mime_type(asset.mime_type)
            or is_supported_video_mime_type(asset.mime_type)
        ):
            return
        source_path = master_path_to_source_path(asset.master_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source file missing for asset {asset.id}")

        output_dir = processed_asset_dir(asset.id)
        tiny_path = output_dir / "tiny.webp"
        include_small = is_supported_video_mime_type(
            asset.mime_type
        ) or should_generate_small_in_api(asset.mime_type, asset.file_size_bytes or 0)
        variants: list[str] = []
        if not tiny_path.is_file():
            variants.append("tiny")
        if include_small and not (output_dir / "small.webp").is_file():
            variants.append("small")
        if not variants:
            return
        write_asset_variants(
            source_path,
            asset.id,
            tuple(variants),
            asset.mime_type,
        )


class EmbeddingBatchProcessor:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.embedding_service = EmbeddingService(session)

    def process_batch(
        self,
        items: list[BatchProcessingItem],
        *,
        force: bool = False,
    ) -> dict[UUID, object]:
        results: dict[UUID, object] = {}
        for item in items:
            try:
                result = self.embedding_service.generate_for_asset(
                    item.asset_id,
                    force=force,
                )
            except Exception as exc:
                results[item.asset_id] = exc
            else:
                results[item.asset_id] = result
        return results


class FaceBatchProcessor:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.face_service = FaceProcessingService(session)

    def process_batch(
        self,
        items: list[BatchProcessingItem],
        *,
        force: bool = False,
    ) -> dict[UUID, object]:
        results: dict[UUID, object] = {}
        for item in items:
            try:
                result = self.face_service.process_asset_faces(
                    item.asset_id,
                    force=force,
                )
            except Exception as exc:
                results[item.asset_id] = exc
            else:
                results[item.asset_id] = result
        return results


def parse_batch_items(items: list[dict[str, str | None]]) -> list[BatchProcessingItem]:
    parsed: list[BatchProcessingItem] = []
    for item in items:
        asset_id_raw = item.get("asset_id")
        if asset_id_raw is None:
            continue
        job_id_raw = item.get("job_id")
        parsed.append(
            BatchProcessingItem(
                asset_id=UUID(asset_id_raw),
                job_id=UUID(job_id_raw) if job_id_raw else None,
            )
        )
    return parsed
