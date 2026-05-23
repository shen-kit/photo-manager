from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.core.database import engine
from app.models import Asset, Job
from app.services.assets.hashing import compute_sha256
from app.services.assets.media import (
    MEDIA_ORIGINALS_DIR,
    canonical_original_path,
    master_path_to_source_path,
    source_path_to_master_path,
)
from app.services.jobs.service import JobService

STORAGE_RULES_COMMIT_BATCH_SIZE = 200
STORAGE_RULES_SAMPLE_FAILURE_LIMIT = 20


@dataclass(frozen=True)
class StorageRuleFailure:
    asset_id: str
    source_master_path: str
    target_master_path: str
    error_code: str
    error_message: str


@dataclass
class StorageRulesStats:
    dry_run: bool
    total_count: int = 0
    processed_count: int = 0
    planned_count: int = 0
    moved_count: int = 0
    reconciled_db_stale_count: int = 0
    already_compliant_count: int = 0
    missing_source_count: int = 0
    conflict_count: int = 0
    invalid_source_path_count: int = 0
    failed_count: int = 0
    batch_commit_failures: int = 0
    failure_counts_by_code: dict[str, int] = field(default_factory=dict)
    sample_failures: list[dict[str, str]] = field(default_factory=list)

    def record_failure(
        self,
        *,
        asset_id: UUID,
        source_master_path: str,
        target_master_path: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self.failed_count += 1
        self.failure_counts_by_code[error_code] = (
            self.failure_counts_by_code.get(error_code, 0) + 1
        )
        if len(self.sample_failures) >= STORAGE_RULES_SAMPLE_FAILURE_LIMIT:
            return
        self.sample_failures.append(
            {
                "asset_id": str(asset_id),
                "source_master_path": source_master_path,
                "target_master_path": target_master_path,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    def as_result(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "total_count": self.total_count,
            "processed_count": self.processed_count,
            "planned_count": self.planned_count,
            "moved_count": self.moved_count,
            "reconciled_db_stale_count": self.reconciled_db_stale_count,
            "already_compliant_count": self.already_compliant_count,
            "missing_source_count": self.missing_source_count,
            "conflict_count": self.conflict_count,
            "invalid_source_path_count": self.invalid_source_path_count,
            "failed_count": self.failed_count,
            "batch_commit_failures": self.batch_commit_failures,
            "failure_counts_by_code": dict(sorted(self.failure_counts_by_code.items())),
            "sample_failures": list(self.sample_failures),
            "succeeded_count": self.moved_count + self.reconciled_db_stale_count,
            "skipped_count": self.already_compliant_count
            + self.missing_source_count
            + self.conflict_count
            + self.invalid_source_path_count,
        }


@dataclass(frozen=True)
class StorageRuleAction:
    kind: str
    target_master_path: str


class StorageRulesExecutionError(RuntimeError):
    pass


class StorageRulesService:
    def run_job(self, *, parent_job_id: UUID, dry_run: bool) -> None:
        asset_ids = self._list_active_asset_ids()
        stats = StorageRulesStats(dry_run=dry_run, total_count=len(asset_ids))
        self._update_job_progress(
            parent_job_id,
            total=stats.total_count,
            message="Planning storage rules" if dry_run else "Applying storage rules",
            result=stats.as_result(),
        )
        if stats.total_count == 0:
            with Session(engine) as session:
                JobService(session).complete_job(
                    parent_job_id,
                    result=stats.as_result(),
                    message="No candidates found",
                )
            return

        pending_db_updates = 0
        processed_since_batch = 0
        with Session(engine) as session:
            for index, asset_id in enumerate(asset_ids, start=1):
                parent_status = self._get_parent_status(parent_job_id)
                if parent_status == "cancelled":
                    self._commit_pending_batch(
                        session=session,
                        parent_job_id=parent_job_id,
                        stats=stats,
                        pending_db_updates=pending_db_updates,
                    )
                    with Session(engine) as cancel_session:
                        JobService(cancel_session).cancel_job(
                            parent_job_id,
                            message=(
                                f"Storage rules cancelled after "
                                f"{stats.processed_count}/{stats.total_count} assets"
                            ),
                            result=stats.as_result(),
                        )
                    return

                asset = session.get(Asset, asset_id)
                if asset is None or asset.deleted_at is not None:
                    stats.processed_count += 1
                    processed_since_batch += 1
                    continue

                source_master_path = asset.master_path
                source_path, target_path, target_master_path = (
                    self._resolve_paths_for_asset(asset)
                )
                try:
                    action = self._reconcile_asset(
                        asset=asset,
                        source_path=source_path,
                        target_path=target_path,
                        target_master_path=target_master_path,
                        dry_run=dry_run,
                    )
                except StorageRulesExecutionError as exc:
                    stats.record_failure(
                        asset_id=asset.id,
                        source_master_path=source_master_path,
                        target_master_path=target_master_path,
                        error_code="move_failed",
                        error_message=str(exc),
                    )
                    stats.processed_count += 1
                    processed_since_batch += 1
                    continue

                self._apply_action_to_stats(stats, action=action)
                if action.kind in {"moved", "reconciled_db_stale"}:
                    session.add(asset)
                    pending_db_updates += 1
                stats.processed_count += 1
                processed_since_batch += 1

                if processed_since_batch >= STORAGE_RULES_COMMIT_BATCH_SIZE:
                    try:
                        self._commit_pending_batch(
                            session=session,
                            parent_job_id=parent_job_id,
                            stats=stats,
                            pending_db_updates=pending_db_updates,
                        )
                    except StorageRulesExecutionError as exc:
                        stats.batch_commit_failures += 1
                        stats.record_failure(
                            asset_id=asset.id,
                            source_master_path=source_master_path,
                            target_master_path=target_master_path,
                            error_code="batch_commit_failed",
                            error_message=str(exc),
                        )
                        self._fail_parent_job(parent_job_id=parent_job_id, stats=stats)
                        return
                    pending_db_updates = 0
                    processed_since_batch = 0

            if pending_db_updates > 0:
                try:
                    self._commit_pending_batch(
                        session=session,
                        parent_job_id=parent_job_id,
                        stats=stats,
                        pending_db_updates=pending_db_updates,
                    )
                except StorageRulesExecutionError as exc:
                    stats.batch_commit_failures += 1
                    stats.record_failure(
                        asset_id=asset_ids[-1],
                        source_master_path="",
                        target_master_path="",
                        error_code="batch_commit_failed",
                        error_message=str(exc),
                    )
                    self._fail_parent_job(parent_job_id=parent_job_id, stats=stats)
                    return

        self._finalize_parent_job(parent_job_id=parent_job_id, stats=stats)

    def _list_active_asset_ids(self) -> list[UUID]:
        with Session(engine) as session:
            return list(
                session.exec(
                    select(Asset.id)
                    .where(Asset.deleted_at.is_(None))
                    .order_by(Asset.created_at.asc(), Asset.id.asc())
                ).all()
            )

    def _resolve_paths_for_asset(
        self,
        asset: Asset,
    ) -> tuple[Path | None, Path, str]:
        source_path: Path | None
        try:
            source_path = master_path_to_source_path(asset.master_path)
        except ValueError:
            source_path = None
        source_suffix = Path(asset.master_path).suffix.lower()
        target_path = canonical_original_path(
            asset.file_hash,
            source_suffix,
            timestamp=asset.created_at,
        )
        target_master_path = source_path_to_master_path(target_path)
        return source_path, target_path, target_master_path

    def _reconcile_asset(
        self,
        *,
        asset: Asset,
        source_path: Path | None,
        target_path: Path,
        target_master_path: str,
        dry_run: bool,
    ) -> StorageRuleAction:
        if asset.master_path == target_master_path:
            return StorageRuleAction(
                kind="already_compliant", target_master_path=target_master_path
            )

        if source_path is None:
            return StorageRuleAction(
                kind="invalid_source_path",
                target_master_path=target_master_path,
            )

        source_exists = source_path.is_file()
        target_exists = target_path.is_file()

        if source_exists and not target_exists:
            if dry_run:
                return StorageRuleAction(
                    kind="planned", target_master_path=target_master_path
                )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)
            asset.master_path = target_master_path
            return StorageRuleAction(
                kind="moved", target_master_path=target_master_path
            )

        if not source_exists and target_exists:
            asset.master_path = target_master_path
            return StorageRuleAction(
                kind="reconciled_db_stale",
                target_master_path=target_master_path,
            )

        if source_exists and target_exists:
            if self._paths_represent_same_asset(
                source_path=source_path,
                target_path=target_path,
                expected_file_hash=asset.file_hash,
            ):
                if not dry_run:
                    source_path.unlink()
                asset.master_path = target_master_path
                return StorageRuleAction(
                    kind="reconciled_db_stale",
                    target_master_path=target_master_path,
                )
            return StorageRuleAction(
                kind="target_conflict", target_master_path=target_master_path
            )

        return StorageRuleAction(
            kind="missing_source", target_master_path=target_master_path
        )

    @staticmethod
    def _paths_represent_same_asset(
        *,
        source_path: Path,
        target_path: Path,
        expected_file_hash: str,
    ) -> bool:
        try:
            if source_path.samefile(target_path):
                return True
        except OSError:
            return False
        if target_path.stem != expected_file_hash:
            return False
        try:
            return (
                compute_sha256(source_path) == expected_file_hash
                and compute_sha256(target_path) == expected_file_hash
            )
        except OSError:
            return False

    @staticmethod
    def _apply_action_to_stats(
        stats: StorageRulesStats,
        *,
        action: StorageRuleAction,
    ) -> None:
        if action.kind == "planned":
            stats.planned_count += 1
            return
        if action.kind == "moved":
            stats.planned_count += 1
            stats.moved_count += 1
            return
        if action.kind == "reconciled_db_stale":
            stats.reconciled_db_stale_count += 1
            return
        if action.kind == "already_compliant":
            stats.already_compliant_count += 1
            return
        if action.kind == "target_conflict":
            stats.conflict_count += 1
            return
        if action.kind == "missing_source":
            stats.missing_source_count += 1
            return
        if action.kind == "invalid_source_path":
            stats.invalid_source_path_count += 1
            return
        raise RuntimeError(f"Unsupported storage rule action: {action.kind}")

    def _commit_pending_batch(
        self,
        *,
        session: Session,
        parent_job_id: UUID,
        stats: StorageRulesStats,
        pending_db_updates: int,
    ) -> None:
        if pending_db_updates > 0:
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise StorageRulesExecutionError(
                    "Database commit failed after filesystem updates; rerun will reconcile moved files and continue"
                ) from exc
        self._update_job_progress(
            parent_job_id,
            current=stats.processed_count,
            total=stats.total_count,
            message="Applying storage rules"
            if not stats.dry_run
            else "Planning storage rules",
            result=stats.as_result(),
        )

    def _finalize_parent_job(
        self,
        *,
        parent_job_id: UUID,
        stats: StorageRulesStats,
    ) -> None:
        with Session(engine) as session:
            job_service = JobService(session)
            result = stats.as_result()
            if stats.failed_count > 0 or stats.batch_commit_failures > 0:
                job_service.fail_job(
                    parent_job_id,
                    self._build_failure_message(stats),
                    result=result,
                )
                return
            job_service.complete_job(
                parent_job_id,
                result=result,
                message="Storage rules completed",
            )

    def _fail_parent_job(
        self,
        *,
        parent_job_id: UUID,
        stats: StorageRulesStats,
    ) -> None:
        with Session(engine) as session:
            JobService(session).fail_job(
                parent_job_id,
                self._build_failure_message(stats),
                result=stats.as_result(),
            )

    @staticmethod
    def _build_failure_message(stats: StorageRulesStats) -> str:
        if stats.batch_commit_failures > 0:
            return (
                "Storage rules failed during batch commit after "
                f"{stats.processed_count}/{stats.total_count} assets; rerun will reconcile moved files and continue"
            )
        if not stats.failure_counts_by_code:
            return "Storage rules completed with failures"
        parts = [
            f"{count} {code}"
            for code, count in sorted(
                stats.failure_counts_by_code.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        return (
            f"Storage rules failed for {stats.failed_count} assets: {', '.join(parts)}"
        )

    @staticmethod
    def _get_parent_status(parent_job_id: UUID) -> str | None:
        with Session(engine) as session:
            job = session.get(Job, parent_job_id)
            return job.status if job is not None else None

    @staticmethod
    def _update_job_progress(
        job_id: UUID,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with Session(engine) as session:
            job_service = JobService(session)
            job_service.update_progress(
                job_id, current=current, total=total, message=message
            )
            if result is not None:
                job = job_service.get_job(job_id)
                job.result = result
                session.add(job)
                session.commit()
