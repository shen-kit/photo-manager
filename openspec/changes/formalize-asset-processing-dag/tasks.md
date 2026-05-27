## 1. DAG Foundation

- [x] 1.1 Add `backend/app/services/processing_dag/` with code-defined node definitions, dependency metadata, and operation policies.
- [x] 1.2 Add a DAG executor/state layer that evaluates applicability, completion, staleness, retryability, and dependency readiness from `assets`, derived files, `asset_processing`, and model defaults.
- [x] 1.3 Add a DAG scheduling adapter that uses existing dispatcher-backed enqueue helpers and semantic dedupe keys.

## 2. Asset Processing State

- [x] 2.1 Reuse `asset_processing` as the primary per-asset node-state table for DAG nodes.
- [x] 2.2 Add only the minimal schema change needed for abandoned-node recovery, if implementation confirms it is necessary.
- [x] 2.3 Document task-name conventions so node identifiers stay stable across services and migrations.

## 3. Entrypoint Migration

- [x] 3.1 Migrate upload and ingest flows to enter the DAG through shared orchestration instead of ad hoc follow-up enqueueing.
- [x] 3.2 Migrate scan-created and scan-reused asset follow-up processing to shared DAG policies.
- [x] 3.3 Migrate restore follow-up processing to DAG reevaluation for missing or stale nodes only.
- [x] 3.4 Migrate preview request scheduling to preview-node entry with shared state and dedupe semantics.

## 4. Model-sensitive AI Nodes

- [x] 4.1 Migrate CLIP generation and CLIP backfill flows to DAG-managed `clip_embedding` entrypoints.
- [x] 4.2 Migrate face processing and face backfill flows to DAG-managed `face_processing` and optional `face_matching` entrypoints.
- [x] 4.3 Make model-version checks explicit in DAG evaluation so CLIP and face results never mix across model ids.

## 5. Batch and Repair Integration

- [x] 5.1 Keep manual/global jobs as parent schedulers and update them to aggregate progress from DAG entrypoint outcomes.
- [x] 5.2 Refactor integrity repair paths to reuse DAG repair or requeue logic for per-asset derivative, CLIP, and face issues.
- [x] 5.3 Keep clustering, storage rules, and orphan cleanup outside the per-asset DAG.

## 6. Failure Handling and Verification

- [x] 6.1 Add tests for node applicability, dependency resolution, stale detection, retryability, and force behavior.
- [x] 6.2 Add tests for upload, scan, restore, preview, CLIP backfill, and face backfill entry policies over the shared DAG.
- [x] 6.3 Add tests that manual face confirmations, exclusions, and assignments survive reruns and forced face processing.
- [x] 6.4 Add tests for abandoned-node recovery and duplicate active-work suppression.
- [ ] 6.5 Manually verify upload, scan, restore, preview-on-demand, CLIP backfill, and face backfill behavior against a real stack.
