from __future__ import annotations

import hashlib
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import aiofiles
from fastapi import BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.database import engine, get_session
from app.models import Asset, AssetTag, Face, Person, Tag
from app.services.assets.hashing import compute_sha256
from app.services.assets.media import (
    MEDIA_ORIGINALS_DIR,
    MEDIA_ORIGINALS_TMP_DIR,
    MediaInspection,
    VIDEO_PREVIEW_STATUS_PENDING,
    VIDEO_PREVIEW_STATUS_READY,
    build_fast_variants,
    canonical_original_path,
    guess_mime_type,
    inspect_video,
    is_canonical_hashed_original,
    is_supported_image_mime_type,
    is_supported_media_mime_type,
    is_supported_video_mime_type,
    is_temporary_original_path,
    master_path_to_source_path,
    processed_video_preview_path,
    resolve_source_input,
    should_generate_large_preview,
    should_generate_small_in_api,
    source_path_to_master_path,
    validate_supported_media,
)
from app.services.jobs.queue import enqueue_asset_processing_job
from app.services.jobs.queue import enqueue_scan_job
from app.services.jobs.service import JobService
from app.services.notifications.service import NotificationService
from app.services.notifications.types import NotificationCategory, NotificationLevel
from app.services.people.maintenance import PeopleMaintenanceService
from app.services.people.repository import PeopleRepository

logger = logging.getLogger(__name__)


@dataclass
class AssetProcessResult:
    asset: Asset
    queued_job: bool
    created_new: bool


@dataclass(frozen=True)
class AssetScanEnqueueResult:
    job_id: UUID


def active_asset_where():
    return Asset.deleted_at.is_(None)


def _generate_fast_artifacts(
    asset_id: UUID, original_path: Path, include_small: bool
) -> None:
    try:
        with Session(engine) as session:
            asset = session.get(Asset, asset_id)
            if asset is None:
                return
            blurhash_value = build_fast_variants(
                original_path,
                asset_id,
                include_small=include_small,
                mime_type=asset.mime_type,
            )
            asset.blurhash = blurhash_value
            session.add(asset)
            session.commit()
    except Exception:
        logger.exception("Failed to generate fast asset variants for %s", asset_id)


class AssetService:
    def __init__(
        self, session: Session, background_tasks: BackgroundTasks | None = None
    ) -> None:
        self.session = session
        self.background_tasks = background_tasks

    def _create_asset_warning(
        self,
        *,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        NotificationService(self.session).create_notification(
            level=NotificationLevel.WARNING,
            category=NotificationCategory.ASSET,
            title="Asset file failed to process",
            message=message,
            details=details,
        )

    def resolve_original_path(self, file_path: str) -> tuple[str, Path]:
        try:
            return resolve_source_input(file_path)
        except FileNotFoundError as exc:
            self._create_asset_warning(
                message="Original file was not found.",
                details={"path": file_path},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original file was not found",
            ) from exc
        except ValueError as exc:
            self._create_asset_warning(
                message=str(exc),
                details={"path": file_path},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    async def save_upload_to_originals(
        self, upload: UploadFile
    ) -> tuple[Path, str, str]:
        filename = Path(upload.filename or f"{uuid4().hex}.bin")
        suffix = filename.suffix.lower()
        detected_content_type = upload.content_type
        if (
            not detected_content_type
            or detected_content_type == "application/octet-stream"
        ):
            detected_content_type = (
                mimetypes.guess_type(filename.name)[0] or "application/octet-stream"
            )
        if not is_supported_media_mime_type(detected_content_type):
            await upload.close()
            self._create_asset_warning(
                message="Only image and video files are supported.",
                details={"filename": filename.name},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image and video files are supported",
            )

        destination = (MEDIA_ORIGINALS_TMP_DIR / f"{uuid4().hex}.part").resolve()

        try:
            destination.relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError as exc:
            await upload.close()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Upload destination escaped the originals root",
            ) from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()

        try:
            await upload.seek(0)
            async with aiofiles.open(destination, "wb") as target:
                while chunk := await upload.read(1024 * 1024):
                    digest.update(chunk)
                    await target.write(chunk)
        except OSError as exc:
            destination.unlink(missing_ok=True)
            self._create_asset_warning(
                message="Failed to persist uploaded file.",
                details={"filename": filename.name},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist uploaded file",
            ) from exc
        finally:
            await upload.close()

        file_hash = digest.hexdigest()
        final_path = canonical_original_path(file_hash, suffix)
        try:
            final_path.relative_to(MEDIA_ORIGINALS_DIR)
        except ValueError as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Final upload path escaped the originals root",
            ) from exc

        if final_path.exists():
            destination.unlink(missing_ok=True)
            return final_path, file_hash, detected_content_type

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(final_path)
        except OSError as exc:
            destination.unlink(missing_ok=True)
            self._create_asset_warning(
                message="Failed to finalize uploaded file.",
                details={"filename": filename.name},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to finalize uploaded file",
            ) from exc

        return final_path, file_hash, detected_content_type

    async def upload_asset(
        self, upload: UploadFile, user_id: UUID
    ) -> AssetProcessResult:
        (
            saved_path,
            file_hash,
            detected_content_type,
        ) = await self.save_upload_to_originals(upload)
        return await self.process_new_asset(
            str(saved_path),
            user_id,
            uploaded_content_type=detected_content_type,
            precomputed_file_hash=file_hash,
            restore_deleted=True,
        )

    async def ingest_asset_path(
        self, file_path: str, user_id: UUID
    ) -> AssetProcessResult:
        return await self.process_new_asset(file_path, user_id, restore_deleted=True)

    async def enqueue_scan(
        self, requested_by_user_id: UUID | None = None
    ) -> AssetScanEnqueueResult:
        job_service = JobService(self.session)
        notification_service = NotificationService(self.session)
        job = job_service.create_job(
            "scan_library",
            parameters={
                "root": str(MEDIA_ORIGINALS_DIR),
                "requested_by_user_id": str(requested_by_user_id)
                if requested_by_user_id is not None
                else None,
            },
        )
        queued_job = await enqueue_scan_job(job.id)
        if not queued_job:
            job_service.fail_job(job.id, "Failed to enqueue library scan job")
            notification_service.create_notification(
                level=NotificationLevel.ERROR,
                category=NotificationCategory.SCAN,
                title="Scan failed",
                message="The library scan could not be queued.",
                related_job_id=job.id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to enqueue library scan job",
            )
        return AssetScanEnqueueResult(job_id=job.id)

    def list_assets(
        self, *, page: int, page_size: int
    ) -> tuple[
        int,
        list[tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]],
    ]:
        tags_subquery, faces_subquery = self._asset_relations_subqueries()
        total = self.session.exec(
            select(func.count()).select_from(Asset).where(active_asset_where())
        ).one()
        offset = (page - 1) * page_size

        statement = (
            select(
                Asset,
                tags_subquery.c.tags,
                faces_subquery.c.faces,
            )
            .where(active_asset_where())
            .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
            .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
            .order_by(Asset.captured_at.desc().nullslast(), Asset.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = self.session.exec(statement).all()
        return total, rows

    def get_asset_detail(
        self, asset_id: UUID
    ) -> tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        tags_subquery, faces_subquery = self._asset_relations_subqueries()
        statement = (
            select(
                Asset,
                tags_subquery.c.tags,
                faces_subquery.c.faces,
            )
            .where(Asset.id == asset_id, active_asset_where())
            .outerjoin(tags_subquery, tags_subquery.c.asset_id == Asset.id)
            .outerjoin(faces_subquery, faces_subquery.c.asset_id == Asset.id)
        )
        row = self.session.exec(statement).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
            )
        return row

    def update_asset(
        self, asset_id: UUID, updates: dict[str, Any]
    ) -> tuple[Asset, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
        asset = self._get_active_asset_or_404(asset_id)
        for field_name, value in updates.items():
            setattr(asset, field_name, value)
        self.session.add(asset)
        self.session.commit()
        return self.get_asset_detail(asset_id)

    def delete_asset(self, asset_id: UUID) -> None:
        asset = self._get_active_asset_or_404(asset_id)
        people_repository = PeopleRepository(self.session)
        impacted_person_ids = people_repository.list_person_ids_for_asset(asset_id=asset.id)
        asset.deleted_at = datetime.now(timezone.utc)
        self.session.add(asset)
        self.session.commit()
        PeopleMaintenanceService(
            self.session,
            repository=people_repository,
        ).reconcile_people(person_ids=impacted_person_ids)

    async def process_new_asset(
        self,
        file_path: str,
        user_id: UUID,
        *,
        uploaded_content_type: str | None = None,
        precomputed_file_hash: str | None = None,
        restore_deleted: bool = False,
    ) -> AssetProcessResult:
        del user_id

        relative_path, source_path = self.resolve_original_path(file_path)
        mime_type = guess_mime_type(source_path, uploaded_content_type)
        file_hash = precomputed_file_hash or compute_sha256(source_path)
        existing_asset = self.session.exec(
            select(Asset).where(Asset.file_hash == file_hash)
        ).first()
        if existing_asset is not None:
            if existing_asset.deleted_at is not None and restore_deleted:
                width, height, video_metadata = self._inspect_media_or_raise(
                    source_path, mime_type
                )
                relative_path, source_path = self._ensure_canonical_original_location(
                    source_path, file_hash
                )
                return await self._restore_deleted_asset(
                    asset=existing_asset,
                    source_path=source_path,
                    master_path=relative_path,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    video_metadata=video_metadata,
                )
            queued_job = False
            if self._asset_requires_reprocessing(existing_asset):
                existing_asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
                self.session.add(existing_asset)
                self.session.commit()
                self.session.refresh(existing_asset)
                queued_job = await enqueue_asset_processing_job(existing_asset.id)
            self._cleanup_duplicate_source(source_path, existing_asset.master_path)
            return AssetProcessResult(
                asset=existing_asset, queued_job=queued_job, created_new=False
            )

        width, height, video_metadata = self._inspect_media_or_raise(
            source_path, mime_type
        )
        relative_path, source_path = self._ensure_canonical_original_location(
            source_path, file_hash
        )

        asset = Asset(
            file_hash=file_hash,
            master_path=relative_path,
            mime_type=mime_type,
            width=width,
            height=height,
            has_large_preview=should_generate_large_preview(width, height),
            file_size_bytes=source_path.stat().st_size,
            video_codec=video_metadata.video_codec if video_metadata else None,
            audio_codec=video_metadata.audio_codec if video_metadata else None,
            duration_seconds=video_metadata.duration_seconds
            if video_metadata
            else None,
            preview_status=VIDEO_PREVIEW_STATUS_PENDING if video_metadata else None,
        )
        self.session.add(asset)
        try:
            self.session.commit()
            self.session.refresh(asset)
        except IntegrityError:
            self.session.rollback()
            existing_asset = self.session.exec(
                select(Asset).where(Asset.file_hash == file_hash)
            ).first()
            if existing_asset is None:
                raise
            if existing_asset.deleted_at is not None and restore_deleted:
                width, height, video_metadata = self._inspect_media_or_raise(
                    source_path, mime_type
                )
                relative_path, source_path = self._ensure_canonical_original_location(
                    source_path, file_hash
                )
                return await self._restore_deleted_asset(
                    asset=existing_asset,
                    source_path=source_path,
                    master_path=relative_path,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    video_metadata=video_metadata,
                )
            queued_job = False
            if self._asset_requires_reprocessing(existing_asset):
                existing_asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING
                self.session.add(existing_asset)
                self.session.commit()
                self.session.refresh(existing_asset)
                queued_job = await enqueue_asset_processing_job(existing_asset.id)
            self._cleanup_duplicate_source(source_path, existing_asset.master_path)
            return AssetProcessResult(
                asset=existing_asset, queued_job=queued_job, created_new=False
            )

        include_small = is_supported_video_mime_type(
            asset.mime_type
        ) or should_generate_small_in_api(
            asset.mime_type,
            asset.file_size_bytes or 0,
        )
        if is_supported_image_mime_type(
            asset.mime_type
        ) or is_supported_video_mime_type(asset.mime_type):
            if self.background_tasks is None:
                _generate_fast_artifacts(asset.id, source_path, include_small)
            else:
                self.background_tasks.add_task(
                    _generate_fast_artifacts, asset.id, source_path, include_small
                )
        queued_job = await enqueue_asset_processing_job(asset.id)
        return AssetProcessResult(asset=asset, queued_job=queued_job, created_new=True)

    def _get_active_asset_or_404(self, asset_id: UUID) -> Asset:
        asset = self.session.exec(
            select(Asset).where(Asset.id == asset_id, active_asset_where())
        ).first()
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
            )
        return asset

    def _asset_relations_subqueries(self) -> tuple[Any, Any]:
        tags_subquery = (
            select(
                AssetTag.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Tag.id,
                        "name",
                        Tag.name,
                        "path",
                        Tag.path,
                    )
                ).label("tags"),
            )
            .select_from(AssetTag)
            .join(Tag, Tag.id == AssetTag.tag_id)
            .group_by(AssetTag.asset_id)
            .subquery()
        )

        faces_subquery = (
            select(
                Face.asset_id.label("asset_id"),
                func.json_agg(
                    func.json_build_object(
                        "id",
                        Face.id,
                        "person_id",
                        Person.id,
                        "person_name",
                        Person.name,
                    )
                ).label("faces"),
            )
            .select_from(Face)
            .join(Person, Person.id == Face.person_id, isouter=True)
            .where(Face.is_excluded.is_(False))
            .group_by(Face.asset_id)
            .subquery()
        )

        return tags_subquery, faces_subquery

    def _asset_requires_reprocessing(self, asset: Asset) -> bool:
        if not is_supported_video_mime_type(asset.mime_type):
            return False
        if asset.preview_status != VIDEO_PREVIEW_STATUS_READY:
            return True
        if asset.video_codec is None or asset.duration_seconds is None:
            return True
        return not processed_video_preview_path(asset.id).is_file()

    def _inspect_media_or_raise(
        self, source_path: Path, mime_type: str
    ) -> tuple[int | None, int | None, MediaInspection | None]:
        try:
            if is_supported_video_mime_type(mime_type):
                video_metadata = inspect_video(source_path)
                return video_metadata.width, video_metadata.height, video_metadata
            width, height = validate_supported_media(source_path, mime_type)
            return width, height, None
        except ValueError as exc:
            self._cleanup_temporary_source(source_path)
            logger.warning("Rejecting unsupported asset: %s", source_path)
            self._create_asset_warning(
                message=str(exc),
                details={"path": str(source_path)},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{str(exc)}\nAsset path: {source_path}",
            ) from exc

    def _cleanup_temporary_source(self, source_path: Path) -> None:
        if is_temporary_original_path(source_path):
            source_path.unlink(missing_ok=True)

    def _cleanup_duplicate_source(
        self, source_path: Path, existing_master_path: str
    ) -> None:
        self._cleanup_temporary_source(source_path)

        try:
            existing_source_path = master_path_to_source_path(existing_master_path)
        except ValueError:
            return

        try:
            source_master_path = source_path_to_master_path(source_path)
        except ValueError:
            return

        if (
            source_path == existing_source_path
            or source_master_path == existing_master_path
        ):
            return
        source_path.unlink(missing_ok=True)

    def _ensure_canonical_original_location(
        self, source_path: Path, file_hash: str
    ) -> tuple[str, Path]:
        if is_canonical_hashed_original(source_path, file_hash):
            return source_path_to_master_path(source_path), source_path

        destination = canonical_original_path(file_hash, source_path.suffix)
        if destination == source_path:
            return source_path_to_master_path(source_path), source_path

        if destination.exists():
            self._cleanup_temporary_source(source_path)
            return source_path_to_master_path(destination), destination

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(destination)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=exc.strerror,
            ) from exc
        return source_path_to_master_path(destination), destination

    async def _restore_deleted_asset(
        self,
        *,
        asset: Asset,
        source_path: Path,
        master_path: str,
        mime_type: str,
        width: int | None,
        height: int | None,
        video_metadata: MediaInspection | None,
    ) -> AssetProcessResult:
        asset.master_path = master_path
        asset.mime_type = mime_type
        asset.width = width
        asset.height = height
        asset.has_large_preview = should_generate_large_preview(width, height)
        asset.file_size_bytes = source_path.stat().st_size
        asset.video_codec = video_metadata.video_codec if video_metadata else None
        asset.audio_codec = video_metadata.audio_codec if video_metadata else None
        asset.duration_seconds = (
            video_metadata.duration_seconds if video_metadata else None
        )
        asset.preview_status = VIDEO_PREVIEW_STATUS_PENDING if video_metadata else None
        asset.deleted_at = None
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)

        include_small = is_supported_video_mime_type(
            asset.mime_type
        ) or should_generate_small_in_api(
            asset.mime_type,
            asset.file_size_bytes or 0,
        )
        if is_supported_image_mime_type(
            asset.mime_type
        ) or is_supported_video_mime_type(asset.mime_type):
            if self.background_tasks is None:
                _generate_fast_artifacts(asset.id, source_path, include_small)
            else:
                self.background_tasks.add_task(
                    _generate_fast_artifacts, asset.id, source_path, include_small
                )
        queued_job = await enqueue_asset_processing_job(asset.id)
        return AssetProcessResult(asset=asset, queued_job=queued_job, created_new=False)


def get_asset_service(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AssetService:
    return AssetService(session=session, background_tasks=background_tasks)
