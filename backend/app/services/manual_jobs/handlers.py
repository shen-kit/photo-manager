from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Asset, Job, Person
from app.services.ai_models.repository import (
    AI_MODEL_TASK_CLIP_EMBEDDING,
    AI_MODEL_TASK_FACE_RECOGNITION,
    AIModelRepository,
)
from app.services.asset_processing.service import AssetProcessingTrackerService
from app.services.assets.scan import scan_originals_library
from app.services.assets.storage_rules import StorageRulesService
from app.services.embeddings.service import EmbeddingService
from app.services.faces.service import FaceProcessingService
from app.services.jobs.dispatcher import (
    INTENT_BACKFILL,
    PROCESS_ASSET_FACES_JOB_NAME,
    PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
    clip_dedup_key,
    faces_dedup_key,
    params_hash,
    queue_for_task,
    thumbnail_batch_dedup_key,
)
from app.services.jobs.queue import (
    enqueue_asset_embedding_batch_job,
    enqueue_asset_faces_batch_job,
    enqueue_asset_thumbnail_batch_job,
)
from app.services.jobs.service import JobService
from app.services.people.repository import PeopleRepository
from app.services.people.thumbnails import PersonThumbnailService
from app.services.people_clustering.service import (
    CLUSTER_DISTANCE_THRESHOLD,
    CLUSTER_MIN_SIZE,
    CLUSTER_TOP_K,
)
from app.services.people_clustering.tasks import cluster_faces
from app.services.processing_dag import AssetProcessingDagService


@dataclass(frozen=True)
class ManualJobParameterDefinition:
    name: str
    type: str
    description: str | None = None
    required: bool = False
    default: Any | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None


@dataclass(frozen=True)
class ManualJobPreparedRun:
    payload: dict[str, Any]
    progress_total: int | None = None
    candidate_ids: list[UUID] | None = None


@dataclass(frozen=True)
class ManualJobDefinition:
    job_key: str
    title: str
    description: str
    category: str
    mode: str
    supports_dry_run: bool
    batch_size: int | None = None
    execution_backend: str = "worker"


class ManualJobHandler:
    definition: ManualJobDefinition
    parameters: tuple[ManualJobParameterDefinition, ...] = ()

    def __init__(self, session: Session) -> None:
        self.session = session
        self.job_service = JobService(session)

    def default_payload(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.default is not None:
                defaults[parameter.name] = parameter.default
        return defaults

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_names = {parameter.name for parameter in self.parameters}
        unexpected = sorted(set(payload) - allowed_names)
        if unexpected:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported params for {self.definition.job_key}: {', '.join(unexpected)}",
            )
        normalized = self.default_payload()
        normalized.update(payload)
        missing = [
            parameter.name
            for parameter in self.parameters
            if parameter.required and parameter.name not in normalized
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required params for {self.definition.job_key}: {', '.join(missing)}",
            )
        return normalized

    def inject_internal_payload(
        self,
        payload: dict[str, Any],
        *,
        requested_by_user_id: UUID | None,
    ) -> dict[str, Any]:
        del requested_by_user_id
        return payload

    def prepare_run(self, payload: dict[str, Any]) -> ManualJobPreparedRun:
        return ManualJobPreparedRun(
            payload=payload,
            progress_total=self.count_candidates(payload),
        )

    def count_candidates(self, payload: dict[str, Any]) -> int | None:
        raise NotImplementedError

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        raise NotImplementedError

    async def schedule_batch(
        self,
        parent_job: Job,
        payload: dict[str, Any],
        asset_ids: list[UUID],
    ) -> None:
        raise NotImplementedError

    def build_zero_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "total_count": 0,
            "processed_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
        }

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        raise NotImplementedError


class BulkScanManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="bulk_scan",
        title="Bulk Scan",
        description="Scan originals storage for new media and enqueue processing.",
        category="asset",
        mode="global",
        supports_dry_run=False,
    )

    def count_candidates(self, payload: dict[str, Any]) -> int | None:
        del payload
        return None

    def inject_internal_payload(
        self,
        payload: dict[str, Any],
        *,
        requested_by_user_id: UUID | None,
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["requested_by_user_id"] = (
            str(requested_by_user_id) if requested_by_user_id is not None else None
        )
        return normalized

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        del prepared_run
        await scan_originals_library({}, str(parent_job.id))

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        return parent_job.result or self.build_zero_result({})


class ClusterFacesManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="cluster_faces",
        title="Cluster Faces",
        description="Cluster current unassigned faces into people.",
        category="face",
        mode="global",
        supports_dry_run=False,
    )
    parameters = (
        ManualJobParameterDefinition(
            name="threshold",
            type="number",
            description="Maximum cosine distance for linking faces into a cluster graph.",
            default=CLUSTER_DISTANCE_THRESHOLD,
            minimum=0.2,
            maximum=0.8,
            step=0.05,
        ),
        ManualJobParameterDefinition(
            name="top_k",
            type="integer",
            description="Number of nearest neighbours to inspect per face.",
            default=CLUSTER_TOP_K,
            minimum=5,
            maximum=100,
            step=1,
        ),
        ManualJobParameterDefinition(
            name="min_cluster_size",
            type="integer",
            description="Minimum connected-component size to materialize as a person.",
            default=CLUSTER_MIN_SIZE,
            minimum=2,
            maximum=20,
            step=1,
        ),
    )

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_payload(payload)
        threshold = float(normalized["threshold"])
        top_k = int(normalized["top_k"])
        min_cluster_size = int(normalized["min_cluster_size"])
        if not 0.2 <= threshold <= 0.8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="threshold must be between 0.2 and 0.8",
            )
        if not 5 <= top_k <= 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="top_k must be between 5 and 100",
            )
        if not 2 <= min_cluster_size <= 20:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_cluster_size must be between 2 and 20",
            )
        return {
            "threshold": threshold,
            "top_k": top_k,
            "min_cluster_size": min_cluster_size,
        }

    def count_candidates(self, payload: dict[str, Any]) -> int | None:
        del payload
        return None

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        payload = prepared_run.payload
        await cluster_faces(
            {},
            str(parent_job.id),
            payload.get("threshold", CLUSTER_DISTANCE_THRESHOLD),
            payload.get("top_k", CLUSTER_TOP_K),
            payload.get("min_cluster_size", CLUSTER_MIN_SIZE),
        )

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        return parent_job.result or self.build_zero_result({})


class RegenerateMissingAssetThumbnailsManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="regenerate_missing_asset_thumbnails",
        title="Regenerate Asset Thumbnails",
        description="Regenerate missing previews and thumbnails for active assets.",
        category="asset",
        mode="batched",
        supports_dry_run=False,
        batch_size=250,
    )

    def _candidate_assets(self) -> list[Asset]:
        dag = AssetProcessingDagService(self.session)
        assets = list(
            self.session.exec(
                select(Asset)
                .where(Asset.deleted_at.is_(None))
                .order_by(Asset.created_at.asc(), Asset.id.asc())
            ).all()
        )
        candidates: list[Asset] = []
        for asset in assets:
            plan = dag.plan_scan_asset(asset.id)
            if plan.require_tiny_thumbnail or plan.require_small_thumbnail:
                candidates.append(asset)
        return candidates

    def count_candidates(self, payload: dict[str, Any]) -> int:
        del payload
        return len(self._candidate_assets())

    def prepare_run(self, payload: dict[str, Any]) -> ManualJobPreparedRun:
        del payload
        candidates = self._candidate_assets()
        return ManualJobPreparedRun(
            payload={},
            progress_total=len(candidates),
            candidate_ids=[asset.id for asset in candidates],
        )

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        self.job_service.update_progress(
            parent_job.id, total=prepared_run.progress_total
        )
        parent_job.progress_message = "Scheduling asset thumbnail regeneration"
        self.session.add(parent_job)
        self.session.commit()

    async def schedule_batch(
        self,
        parent_job: Job,
        payload: dict[str, Any],
        asset_ids: list[UUID],
    ) -> None:
        del payload
        for asset_id in asset_ids:
            existing_child = self.job_service.get_child_job_for_asset(
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
            )
            if existing_child is not None:
                continue
            child = self.job_service.create_job(
                "process_asset_thumbnail_batch_item",
                parameters={"asset_id": str(asset_id)},
                job_key=parent_job.job_key,
                queue_name=queue_for_task(
                    job_name=PROCESS_ASSET_THUMBNAIL_BATCH_JOB_NAME,
                    intent=INTENT_BACKFILL,
                ),
                intent=INTENT_BACKFILL,
                dedup_key=thumbnail_batch_dedup_key(asset_ids=[str(asset_id)]),
                params_hash=params_hash({"asset_id": str(asset_id)}),
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
                is_visible=False,
            )
        queued = await enqueue_asset_thumbnail_batch_job(
            [
                {"asset_id": str(asset_id), "job_id": str(child.id)}
                for asset_id, child in [
                    (
                        asset_id,
                        self.job_service.get_child_job_for_asset(
                            parent_job_id=parent_job.id,
                            related_asset_id=asset_id,
                        ),
                    )
                    for asset_id in asset_ids
                ]
                if child is not None
            ],
            intent=INTENT_BACKFILL,
        )
        if not queued:
            for asset_id in asset_ids:
                child = self.job_service.get_child_job_for_asset(
                    parent_job_id=parent_job.id,
                    related_asset_id=asset_id,
                )
                if child is None:
                    continue
                self.job_service.fail_job(
                    child.id,
                    "Failed to enqueue thumbnail batch job",
                    result={"asset_id": str(asset_id), "skipped": False},
                )

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        children = self.job_service.list_child_jobs(parent_job_id=parent_job.id)
        failed_count = sum(1 for child in children if child.status == "failed")
        succeeded_count = sum(1 for child in children if child.status == "completed")
        return {
            "total_count": parent_job.progress_total or 0,
            "processed_count": len(children),
            "succeeded_count": succeeded_count,
            "failed_count": failed_count,
            "skipped_count": 0,
        }


class RegenerateMissingPeopleThumbnailsManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="regenerate_missing_people_thumbnails",
        title="Regenerate People Thumbnails",
        description="Regenerate missing person thumbnail files.",
        category="people",
        mode="global",
        supports_dry_run=False,
    )

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.people_repository = PeopleRepository(session)
        self.thumbnail_service = PersonThumbnailService(session)

    def _candidate_people(self) -> list[Person]:
        rows = self.people_repository.list_people(include_hidden=True, search=None)
        candidates: list[Person] = []
        for row in rows:
            person = row.person
            if person.thumbnail_path is None:
                candidates.append(person)
                continue
            thumbnail_path = (
                self.thumbnail_service.processed_dir / person.thumbnail_path
            )
            if not thumbnail_path.is_file():
                candidates.append(person)
                continue
            if person.thumbnail_manually_set and person.thumbnail_face_id is not None:
                candidate = self.people_repository.get_thumbnail_candidate(
                    person_id=person.id,
                    face_id=person.thumbnail_face_id,
                )
                if candidate is None:
                    candidates.append(person)
        return candidates

    def count_candidates(self, payload: dict[str, Any]) -> int:
        del payload
        return len(self._candidate_people())

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        del prepared_run
        people = self._candidate_people()
        self.job_service.mark_running(
            parent_job.id, message="Regenerating missing people thumbnails"
        )
        self.job_service.update_progress(parent_job.id, total=len(people))
        regenerated_count = 0
        failed_count = 0
        cleared_count = 0
        for index, person in enumerate(people, start=1):
            try:
                result = self.thumbnail_service.ensure_thumbnail(person_id=person.id)
            except Exception as exc:
                failed_count += 1
                message = (
                    f"Failed to regenerate thumbnail for person {person.id}: {exc}"
                )
                self.job_service.update_progress(
                    parent_job.id,
                    current=index,
                    message=message,
                )
                continue
            if result.thumbnail_path is None:
                cleared_count += 1
            else:
                regenerated_count += 1
            self.job_service.update_progress(
                parent_job.id,
                current=index,
                message=f"Processed {index}/{len(people)} people thumbnails",
            )
        result = {
            "total_count": len(people),
            "processed_count": len(people),
            "succeeded_count": regenerated_count,
            "failed_count": failed_count,
            "skipped_count": 0,
            "regenerated_count": regenerated_count,
            "cleared_count": cleared_count,
        }
        if failed_count:
            self.job_service.fail_job(
                parent_job.id,
                "People thumbnail regeneration completed with failures",
                result=result,
            )
        else:
            self.job_service.complete_job(
                parent_job.id,
                result=result,
                message="People thumbnail regeneration completed",
            )

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        return parent_job.result or self.build_zero_result({})


class ApplyStorageRulesManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="apply_storage_rules",
        title="Apply Storage Rules",
        description="Plan or apply canonical originals storage moves.",
        category="asset",
        mode="global",
        supports_dry_run=True,
        execution_backend="api",
    )
    parameters = (
        ManualJobParameterDefinition(
            name="dry_run",
            type="boolean",
            description="Preview storage moves without changing files or database paths.",
            default=True,
        ),
    )

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_payload(payload)
        dry_run = bool(normalized["dry_run"])
        return {"dry_run": dry_run}

    def count_candidates(self, payload: dict[str, Any]) -> int | None:
        del payload
        return None

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        dry_run = bool(prepared_run.payload.get("dry_run", True))
        StorageRulesService().run_job(parent_job_id=parent_job.id, dry_run=dry_run)

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        return parent_job.result or self.build_zero_result({})


class RunMissingOrOutdatedClipEmbeddingsManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="run_missing_or_outdated_clip_embeddings",
        title="Run CLIP Embeddings",
        description="Generate missing or outdated CLIP embeddings for the current default model.",
        category="search",
        mode="batched",
        supports_dry_run=False,
        batch_size=100,
    )
    parameters = (
        ManualJobParameterDefinition(
            name="force",
            type="boolean",
            description="Rebuild embeddings even when the current default model appears complete.",
            default=False,
        ),
    )

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.embedding_service = EmbeddingService(session)
        self.ai_model_repository = AIModelRepository(session)
        self.tracker = AssetProcessingTrackerService(session)

    def _candidate_asset_ids(self, *, force: bool) -> tuple[int, list[UUID]]:
        model_id, asset_ids = self.embedding_service.list_missing_asset_ids(force=force)
        dag = AssetProcessingDagService(self.session)
        filtered: list[UUID] = []
        for asset_id in asset_ids:
            asset = dag.state.get_asset(asset_id)
            if asset is None:
                continue
            node = dag.evaluate(
                asset=asset,
                task=AI_MODEL_TASK_CLIP_EMBEDDING,
                force=force,
            )
            if force or node.needs_processing:
                filtered.append(asset_id)
        return model_id, filtered

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_payload(payload)
        return {"force": bool(normalized["force"])}

    def prepare_run(self, payload: dict[str, Any]) -> ManualJobPreparedRun:
        force = bool(payload.get("force", False))
        _, asset_ids = self._candidate_asset_ids(force=force)
        return ManualJobPreparedRun(
            payload={"force": force},
            progress_total=len(asset_ids),
            candidate_ids=asset_ids,
        )

    def count_candidates(self, payload: dict[str, Any]) -> int:
        force = bool(payload.get("force", False))
        _, asset_ids = self._candidate_asset_ids(force=force)
        return len(asset_ids)

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        self.job_service.update_progress(
            parent_job.id, total=prepared_run.progress_total
        )
        self.job_service.mark_running(
            parent_job.id, message="Scheduling CLIP embedding jobs"
        )

    async def schedule_batch(
        self,
        parent_job: Job,
        payload: dict[str, Any],
        asset_ids: list[UUID],
    ) -> None:
        force = bool(payload.get("force", False))
        clip_model = self.ai_model_repository.get_default_model_for_task(
            AI_MODEL_TASK_CLIP_EMBEDDING
        )
        dag = AssetProcessingDagService(self.session)
        for asset_id in asset_ids:
            asset = dag.state.get_asset(asset_id)
            if asset is None:
                continue
            if not force and not dag.evaluate(
                asset=asset,
                task=AI_MODEL_TASK_CLIP_EMBEDDING,
            ).needs_processing:
                continue
            existing_child = self.job_service.get_child_job_for_asset(
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
            )
            if existing_child is not None:
                continue
            child = self.job_service.create_job(
                "generate_asset_clip_embedding",
                parameters={"asset_id": str(asset_id), "force": force},
                job_key=parent_job.job_key,
                queue_name=queue_for_task(
                    job_name="generate_asset_clip_embedding",
                    intent=INTENT_BACKFILL,
                ),
                intent=INTENT_BACKFILL,
                dedup_key=clip_dedup_key(asset_id, model_id=clip_model.id),
                params_hash=params_hash({"asset_id": str(asset_id), "force": force}),
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
                is_visible=False,
            )
            self.tracker.mark_queued(
                asset_id=asset_id,
                ai_model_id=clip_model.id,
                task=AI_MODEL_TASK_CLIP_EMBEDDING,
                job_id=child.id,
            )
        queued = await enqueue_asset_embedding_batch_job(
            [
                {
                    "asset_id": str(asset_id),
                    "job_id": str(
                        self.job_service.get_child_job_for_asset(
                            parent_job_id=parent_job.id,
                            related_asset_id=asset_id,
                        ).id
                    ),
                }
                for asset_id in asset_ids
                if self.job_service.get_child_job_for_asset(
                    parent_job_id=parent_job.id,
                    related_asset_id=asset_id,
                )
                is not None
            ],
            force=force,
            intent=INTENT_BACKFILL,
        )
        if not queued:
            for asset_id in asset_ids:
                child = self.job_service.get_child_job_for_asset(
                    parent_job_id=parent_job.id,
                    related_asset_id=asset_id,
                )
                if child is None:
                    continue
                self.tracker.mark_failed(
                    asset_id=asset_id,
                    ai_model_id=clip_model.id,
                    task=AI_MODEL_TASK_CLIP_EMBEDDING,
                    job_id=child.id,
                    error_message="Failed to enqueue CLIP embedding batch job",
                )
                self.job_service.fail_job(
                    child.id,
                    "Failed to enqueue CLIP embedding batch job",
                    result={"asset_id": str(asset_id), "skipped": False},
                )

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        children = self.job_service.list_child_jobs(parent_job_id=parent_job.id)
        failed_count = 0
        succeeded_count = 0
        skipped_count = 0
        generated_count = 0
        for child in children:
            if child.status == "failed":
                failed_count += 1
                continue
            if child.status != "completed":
                continue
            result = child.result or {}
            if bool(result.get("skipped")):
                skipped_count += 1
                continue
            succeeded_count += 1
            generated_count += int(bool(result.get("generated", False)))
        return {
            "total_count": parent_job.progress_total or 0,
            "processed_count": len(children),
            "succeeded_count": succeeded_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "generated_count": generated_count,
        }


class RunMissingOrOutdatedFaceRecognitionManualJobHandler(ManualJobHandler):
    definition = ManualJobDefinition(
        job_key="run_missing_or_outdated_face_recognition",
        title="Run Face Recognition",
        description="Run face detection for assets missing or outdated for the current default model.",
        category="face",
        mode="batched",
        supports_dry_run=False,
        batch_size=50,
    )
    parameters = (
        ManualJobParameterDefinition(
            name="force",
            type="boolean",
            description="Re-run face processing even when the current model appears complete.",
            default=False,
        ),
        ManualJobParameterDefinition(
            name="auto_match",
            type="boolean",
            description="Run incremental face matching after successful detection.",
            default=False,
        ),
    )

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.face_service = FaceProcessingService(session)
        self.ai_model_repository = AIModelRepository(session)
        self.tracker = AssetProcessingTrackerService(session)

    def _candidate_asset_ids(
        self,
        *,
        force: bool,
        auto_match: bool,
    ) -> tuple[int, list[UUID]]:
        model_id, asset_ids = self.face_service.list_asset_ids_pending_face_processing(
            force=force
        )
        dag = AssetProcessingDagService(self.session)
        filtered: list[UUID] = []
        for asset_id in asset_ids:
            asset = dag.state.get_asset(asset_id)
            if asset is None:
                continue
            node = dag.evaluate(
                asset=asset,
                task=AI_MODEL_TASK_FACE_RECOGNITION,
                force=force,
                require_face_match=auto_match,
            )
            if force or node.needs_processing:
                filtered.append(asset_id)
        return model_id, filtered

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_payload(payload)
        return {
            "force": bool(normalized["force"]),
            "auto_match": bool(normalized["auto_match"]),
        }

    def prepare_run(self, payload: dict[str, Any]) -> ManualJobPreparedRun:
        force = bool(payload.get("force", False))
        auto_match = bool(payload.get("auto_match", False))
        _, asset_ids = self._candidate_asset_ids(force=force, auto_match=auto_match)
        return ManualJobPreparedRun(
            payload={"force": force, "auto_match": auto_match},
            progress_total=len(asset_ids),
            candidate_ids=asset_ids,
        )

    def count_candidates(self, payload: dict[str, Any]) -> int:
        force = bool(payload.get("force", False))
        auto_match = bool(payload.get("auto_match", False))
        _, asset_ids = self._candidate_asset_ids(force=force, auto_match=auto_match)
        return len(asset_ids)

    async def run_parent_job(
        self,
        parent_job: Job,
        prepared_run: ManualJobPreparedRun,
    ) -> None:
        self.job_service.update_progress(
            parent_job.id, total=prepared_run.progress_total
        )
        self.job_service.mark_running(
            parent_job.id, message="Scheduling face recognition jobs"
        )

    async def schedule_batch(
        self,
        parent_job: Job,
        payload: dict[str, Any],
        asset_ids: list[UUID],
    ) -> None:
        force = bool(payload.get("force", False))
        auto_match = bool(payload.get("auto_match", False))
        face_model = self.ai_model_repository.get_default_model_for_task(
            AI_MODEL_TASK_FACE_RECOGNITION
        )
        dag = AssetProcessingDagService(self.session)
        for asset_id in asset_ids:
            asset = dag.state.get_asset(asset_id)
            if asset is None:
                continue
            if not force and not dag.evaluate(
                asset=asset,
                task=AI_MODEL_TASK_FACE_RECOGNITION,
                require_face_match=auto_match,
            ).needs_processing:
                continue
            existing_child = self.job_service.get_child_job_for_asset(
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
            )
            if existing_child is not None:
                continue
            child = self.job_service.create_job(
                "process_asset_faces",
                parameters={
                    "asset_id": str(asset_id),
                    "force": force,
                    "auto_match": auto_match,
                },
                job_key=parent_job.job_key,
                queue_name=queue_for_task(
                    job_name=PROCESS_ASSET_FACES_JOB_NAME,
                    intent=INTENT_BACKFILL,
                ),
                intent=INTENT_BACKFILL,
                dedup_key=faces_dedup_key(
                    asset_id,
                    model_id=face_model.id,
                    auto_match=auto_match,
                ),
                params_hash=params_hash(
                    {
                        "asset_id": str(asset_id),
                        "force": force,
                        "auto_match": auto_match,
                    }
                ),
                parent_job_id=parent_job.id,
                related_asset_id=asset_id,
                is_visible=False,
            )
            self.tracker.mark_queued(
                asset_id=asset_id,
                ai_model_id=face_model.id,
                task=AI_MODEL_TASK_FACE_RECOGNITION,
                job_id=child.id,
            )
        queued = await enqueue_asset_faces_batch_job(
            [
                {
                    "asset_id": str(asset_id),
                    "job_id": str(
                        self.job_service.get_child_job_for_asset(
                            parent_job_id=parent_job.id,
                            related_asset_id=asset_id,
                        ).id
                    ),
                }
                for asset_id in asset_ids
                if self.job_service.get_child_job_for_asset(
                    parent_job_id=parent_job.id,
                    related_asset_id=asset_id,
                )
                is not None
            ],
            force=force,
            auto_match=auto_match,
            intent=INTENT_BACKFILL,
        )
        if not queued:
            for asset_id in asset_ids:
                child = self.job_service.get_child_job_for_asset(
                    parent_job_id=parent_job.id,
                    related_asset_id=asset_id,
                )
                if child is None:
                    continue
                self.tracker.mark_failed(
                    asset_id=asset_id,
                    ai_model_id=face_model.id,
                    task=AI_MODEL_TASK_FACE_RECOGNITION,
                    job_id=child.id,
                    error_message="Failed to enqueue face recognition batch job",
                )
                self.job_service.fail_job(
                    child.id,
                    "Failed to enqueue face recognition batch job",
                    result={"asset_id": str(asset_id), "skipped": False},
                )

    def build_parent_result(self, parent_job: Job) -> dict[str, Any]:
        children = self.job_service.list_child_jobs(parent_job_id=parent_job.id)
        failed_count = 0
        succeeded_count = 0
        skipped_count = 0
        faces_created = 0
        faces_matched = 0
        zero_face_assets = 0
        for child in children:
            if child.status == "failed":
                failed_count += 1
                continue
            if child.status != "completed":
                continue
            result = child.result or {}
            if bool(result.get("skipped")):
                skipped_count += 1
                continue
            succeeded_count += 1
            faces_created += int(result.get("faces_created", 0) or 0)
            faces_matched += int(result.get("faces_matched", 0) or 0)
            if int(result.get("detected_faces", 0) or 0) == 0:
                zero_face_assets += 1
        return {
            "total_count": parent_job.progress_total or 0,
            "processed_count": len(children),
            "succeeded_count": succeeded_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "faces_created": faces_created,
            "faces_matched": faces_matched,
            "zero_face_assets": zero_face_assets,
        }


MANUAL_JOB_HANDLER_TYPES = (
    BulkScanManualJobHandler,
    RegenerateMissingAssetThumbnailsManualJobHandler,
    ClusterFacesManualJobHandler,
    RegenerateMissingPeopleThumbnailsManualJobHandler,
    ApplyStorageRulesManualJobHandler,
    RunMissingOrOutdatedClipEmbeddingsManualJobHandler,
    RunMissingOrOutdatedFaceRecognitionManualJobHandler,
)
