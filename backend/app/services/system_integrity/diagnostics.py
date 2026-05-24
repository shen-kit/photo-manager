from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from app.models import Asset, Person
from app.services.assets.media import (
    MEDIA_ORIGINALS_DIR,
    MEDIA_PROCESSED_DIR,
    master_path_to_source_path,
    processed_asset_dir,
    processed_video_preview_path,
)
from app.services.embeddings.service import EmbeddingService
from app.services.faces.service import FaceProcessingService
from app.services.people.repository import PeopleRepository


@dataclass(frozen=True)
class DiagnosticEvaluation:
    health_state: str
    summary: dict[str, object]
    items: list[dict[str, object]]


def _health_state_for_count(count: int) -> str:
    return "healthy" if count == 0 else "warning"


def evaluate_check_originals_exist(session: Session) -> DiagnosticEvaluation:
    items: list[dict[str, object]] = []
    for asset in session.exec(select(Asset).where(Asset.deleted_at.is_(None))).all():
        try:
            source_path = master_path_to_source_path(asset.master_path)
        except ValueError:
            items.append(
                {
                    "asset_id": asset.id,
                    "item_type": "asset",
                    "reason_code": "invalid_master_path",
                    "repairable": False,
                    "detail_json": {"master_path": asset.master_path},
                }
            )
            continue
        if not source_path.is_file():
            items.append(
                {
                    "asset_id": asset.id,
                    "relative_path": asset.master_path,
                    "item_type": "asset",
                    "reason_code": "missing_original",
                    "repairable": False,
                    "detail_json": {"master_path": asset.master_path},
                }
            )
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )


def evaluate_check_asset_derivatives(session: Session) -> DiagnosticEvaluation:
    items: list[dict[str, object]] = []
    counts = {"tiny": 0, "small": 0, "large": 0, "video_preview": 0}
    assets = session.exec(select(Asset).where(Asset.deleted_at.is_(None))).all()
    for asset in assets:
        asset_dir = processed_asset_dir(asset.id)
        expected_files: list[tuple[str, Path]] = [
            ("tiny", asset_dir / "tiny.webp"),
            ("small", asset_dir / "small.webp"),
        ]
        if asset.has_large_preview:
            expected_files.append(("large", asset_dir / "large.webp"))
        if asset.media_kind == "video":
            expected_files.append(("video_preview", processed_video_preview_path(asset.id)))
        missing = [name for name, path in expected_files if not path.is_file()]
        for name in missing:
            counts[name] += 1
        if missing:
            items.append(
                {
                    "asset_id": asset.id,
                    "item_type": "asset",
                    "reason_code": "missing_derivatives",
                    "repairable": True,
                    "detail_json": {"missing_derivatives": missing},
                }
            )
    affected_count = len(items)
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(affected_count),
        summary={"affected_count": affected_count, "subtype_counts": counts},
        items=items,
    )


def evaluate_check_clip_embeddings(session: Session) -> DiagnosticEvaluation:
    _, asset_ids = EmbeddingService(session).list_missing_asset_ids(force=False)
    items = [
        {
            "asset_id": asset_id,
            "item_type": "asset",
            "reason_code": "needs_clip_embedding",
            "repairable": True,
            "detail_json": None,
        }
        for asset_id in asset_ids
    ]
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )


def evaluate_check_face_processing(session: Session) -> DiagnosticEvaluation:
    _, asset_ids = FaceProcessingService(session).list_asset_ids_pending_face_processing(
        force=False
    )
    items = [
        {
            "asset_id": asset_id,
            "item_type": "asset",
            "reason_code": "needs_face_processing",
            "repairable": True,
            "detail_json": None,
        }
        for asset_id in asset_ids
    ]
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )


def evaluate_check_original_files_without_db_assets(session: Session) -> DiagnosticEvaluation:
    asset_paths = set(
        session.exec(
            select(Asset.master_path).where(Asset.deleted_at.is_(None))
        ).all()
    )
    items: list[dict[str, object]] = []
    for path in sorted(p for p in MEDIA_ORIGINALS_DIR.rglob("*") if p.is_file()):
        try:
            relative_path = path.relative_to(MEDIA_ORIGINALS_DIR).as_posix()
        except ValueError:
            continue
        if relative_path.startswith(".tmp/"):
            continue
        if relative_path not in asset_paths:
            items.append(
                {
                    "relative_path": relative_path,
                    "item_type": "path",
                    "reason_code": "original_without_asset",
                    "repairable": False,
                    "detail_json": None,
                }
            )
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )


def _expected_processed_paths(session: Session) -> set[str]:
    expected: set[str] = set()
    assets = session.exec(select(Asset).where(Asset.deleted_at.is_(None))).all()
    for asset in assets:
        asset_dir = processed_asset_dir(asset.id)
        expected.add((asset_dir / "tiny.webp").relative_to(MEDIA_PROCESSED_DIR).as_posix())
        expected.add((asset_dir / "small.webp").relative_to(MEDIA_PROCESSED_DIR).as_posix())
        if asset.has_large_preview:
            expected.add((asset_dir / "large.webp").relative_to(MEDIA_PROCESSED_DIR).as_posix())
        if asset.media_kind == "video":
            expected.add(
                processed_video_preview_path(asset.id).relative_to(MEDIA_PROCESSED_DIR).as_posix()
            )
    for person in session.exec(select(Person)).all():
        if person.thumbnail_path:
            expected.add(person.thumbnail_path)
    return expected


def evaluate_check_processed_files_without_db_assets(
    session: Session,
) -> DiagnosticEvaluation:
    expected = _expected_processed_paths(session)
    items: list[dict[str, object]] = []
    for path in sorted(p for p in MEDIA_PROCESSED_DIR.rglob("*") if p.is_file()):
        try:
            relative_path = path.relative_to(MEDIA_PROCESSED_DIR).as_posix()
        except ValueError:
            continue
        if relative_path not in expected:
            items.append(
                {
                    "relative_path": relative_path,
                    "item_type": "path",
                    "reason_code": "processed_without_owner",
                    "repairable": True,
                    "detail_json": None,
                }
            )
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )


def evaluate_check_people_without_active_faces(session: Session) -> DiagnosticEvaluation:
    people_repository = PeopleRepository(session)
    people = people_repository.list_people(include_hidden=True, search=None)
    person_ids = [row.person.id for row in people]
    affected_ids = people_repository.list_person_ids_without_active_assets(
        person_ids=person_ids
    )
    items = [
        {
            "person_id": person_id,
            "item_type": "person",
            "reason_code": "person_without_active_faces",
            "repairable": True,
            "detail_json": None,
        }
        for person_id in affected_ids
    ]
    return DiagnosticEvaluation(
        health_state=_health_state_for_count(len(items)),
        summary={"affected_count": len(items)},
        items=items,
    )
