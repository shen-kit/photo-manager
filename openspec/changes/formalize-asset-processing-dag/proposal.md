## Why

Per-asset processing rules already exist in the backend, but they are expressed indirectly through scattered follow-up enqueue calls in upload, ingest, scan, restore, preview, embedding, face, manual-job, and integrity-repair flows. The result is correct enough to work today, but the dependency model is implicit, duplicated, and harder to reason about when model versions change, retries happen, or new entrypoints are added.

The codebase would be cleaner and more robust with one formal per-asset processing DAG that centralizes dependency rules, stale detection, idempotent execution semantics, and enqueue deduplication decisions while preserving current user-facing behavior.

## What Changes

- Add a shared in-code asset-processing DAG definition for coarse-grained per-asset capabilities.
- Add a DAG orchestration service layer that resolves node state, dependencies, enqueue decisions, and retries.
- Keep worker task entrypoints thin and move follow-up scheduling out of feature services into the DAG orchestrator.
- Reuse `asset_processing` as the primary per-asset node-state table, with only minimal schema changes if needed for crash-safe lease recovery.
- Keep manual/global workflows such as bulk scan, clustering, storage rules, and integrity diagnostics as parent schedulers around DAG entrypoints rather than turning them into DAG nodes.
- Align preview, restore, upload, scan, CLIP backfill, and face backfill with the same DAG semantics while allowing different batching, priority, force, retry, and progress policies.

## Capabilities

### New Capabilities
- `asset-processing-dag`: Centralized per-asset DAG orchestration with shared dependency rules, node staleness evaluation, force policies, crash recovery, and operation-specific entrypoints.

### Modified Capabilities
- `job-dispatching`: Existing dispatcher and dedupe behavior become the preferred enqueue backend for DAG node scheduling rather than ad hoc follow-up calls.

## Impact

- Affected code: `backend/app/services/assets/`, `asset_processing/`, `embeddings/`, `faces/`, `trash/`, `manual_jobs/`, `system_integrity/`, and worker task wrappers.
- Affected schema: likely none or one minimal `asset_processing` addition for lease-based recovery.
- Affected behavior: dependency handling becomes explicit and centralized, duplicate follow-up work is reduced, and retry/recovery behavior becomes more predictable across upload, scan, restore, and preview flows.
- Relationship to active work: this proposal should build on `add-job-deduplication-and-queue-routing`, not replace it.
