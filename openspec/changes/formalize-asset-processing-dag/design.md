## Context

The backend already has most of the ingredients for a formal processing graph:

- durable asset state in PostgreSQL
- per-asset tracker rows in `asset_processing`
- queue dispatch and dedupe helpers in `jobs`
- thin worker entrypoints that delegate to services

What it lacks is one place that answers:

- what work is required for an asset right now
- which node depends on which other node
- whether a node is complete, stale, retryable, or force-required
- which follow-up nodes should be enqueued next

Today those answers are spread across service-specific code paths.

## Current Scattered Follow-up Map

The main follow-up scheduling is currently scattered in these places:

- `backend/app/services/assets/service.py`
  - upload/ingest/re-ingest enqueue `process_asset_metadata`
  - duplicate or restored assets conditionally trigger reprocessing
- `backend/app/services/assets/jobs.py`
  - metadata job directly enqueues CLIP and face jobs
- `backend/app/services/assets/scan.py`
  - scan does inline thumbnail generation, then separately enqueues embedding and face batches
- `backend/app/services/assets/preview.py`
  - preview requests decide inline generation vs queued preview work
- `backend/app/services/trash/service.py`
  - restore independently decides whether to queue metadata, CLIP, faces, or run face matching inline
- `backend/app/services/manual_jobs/handlers.py`
  - thumbnail, CLIP, and face backfills each build their own candidate logic and child-job scheduling rules
- `backend/app/services/system_integrity/tasks.py`
  - repairs call thumbnail, preview, CLIP, and face services directly rather than going through shared orchestration

This is the core design problem. The system already has a graph, but the graph is encoded as side effects in multiple places.

## Recommendation

Implement the formal DAG change.

This will improve code design, maintainability, and robustness because:

- dependency rules move into one location
- upload, scan, restore, preview, and backfills share node semantics
- model-sensitive stale detection becomes explicit instead of reimplemented
- crash recovery has one policy instead of several partial ones
- future node additions stop multiplying follow-up logic across services

Keeping the current design as-is would preserve short-term familiarity, but it would continue to accumulate policy duplication in exactly the areas that need the most correctness and idempotency.

## Architecture

Use one shared in-code per-asset DAG with operation-specific entry policies.

```text
                   ┌──────────────────────┐
                   │ asset discovered     │
                   │ / created / reused   │
                   └──────────┬───────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ metadata_refresh │
                    │ timeline refresh │
                    └────────┬─────────┘
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
      ┌────────────────┐  ┌───────────┐  ┌─────────────────┐
      │ tiny_thumbnail │  │ small_... │  │ face_processing │
      └────────┬───────┘  └─────┬─────┘  └────────┬────────┘
               │                │                 │
               │                │                 ▼
               │                │        ┌─────────────────┐
               │                │        │ face_matching   │
               │                │        │ person upkeep   │
               │                │        └─────────────────┘
               │                │
               │                ├───────────────┐
               │                │               │
               ▼                ▼               ▼
      ┌────────────────┐  ┌──────────────┐  ┌────────────────┐
      │ image_preview  │  │ video_preview│  │ clip_embedding │
      └────────────────┘  └──────────────┘  └────────────────┘
```

Notes:

- `metadata_refresh` is one node that owns metadata extraction plus timeline field refresh.
- `tiny_thumbnail` and `small_thumbnail` are distinct capabilities because they can be independently missing.
- `image_preview` and `video_preview` are separate nodes.
- `clip_embedding` depends on the best available embedding source:
  - image assets: original file
  - video assets: generated thumbnail/preview derivative, so `small_thumbnail` is a dependency
- `face_processing` is the per-asset model-sensitive face detection/write node.
- `face_matching` is an optional follow-up node for incremental assignment and person maintenance.

## Node Boundaries

Use coarse nodes, not rows for every tiny sub-step.

Recommended per-asset DAG nodes:

- `metadata_refresh`
- `tiny_thumbnail`
- `small_thumbnail`
- `image_preview`
- `video_preview`
- `clip_embedding`
- `face_processing`
- `face_matching`

Internal details that should stay inside node executors:

- EXIF parsing and timeline derivation inside `metadata_refresh`
- actual variant file writes inside thumbnail/preview nodes
- confirmed-face preservation and row replacement rules inside `face_processing`
- people thumbnail refresh and person cleanup inside `face_matching` or person maintenance hooks

Out of scope for per-asset DAG nodes:

- bulk scan parent orchestration
- face clustering
- storage-rules application
- integrity diagnostic snapshot generation
- cleanup of processed orphan files

Those remain global/manual workflows, though they may call into DAG repair or enqueue services.

## Operation-specific Entrypoints

All of these use the same DAG definition, but different policies:

- Upload / ingest
  - entrypoint: `metadata_refresh`
  - policy: eager metadata and thumbnail readiness, normal AI follow-up
- Bulk scan
  - entrypoint: `metadata_refresh` for created or reused assets
  - policy: batch scheduling, backfill intent, progress aggregated by parent job
- Restore
  - entrypoint: asset-level reevaluation
  - policy: queue only nodes that are missing or stale; avoid unnecessary work
- Preview request
  - entrypoint: `image_preview` or `video_preview`
  - policy: interactive priority, allow inline fast path for eligible images
- CLIP backfill
  - entrypoint: `clip_embedding`
  - policy: model-sensitive, batched, optional force
- Face backfill
  - entrypoint: `face_processing` and optionally `face_matching`
  - policy: model-sensitive, batched, optional force and auto-match
- Integrity repair
  - entrypoint: specific node or repair plan
  - policy: revalidate before enqueue or execution

## State Model

`asset_processing` is close to sufficient for the DAG if node granularity stays coarse.

Keep `asset_processing` as the main per-asset node-state table keyed by:

- `asset_id`
- `task`
- `ai_model_id` when model-sensitive

Use it to store:

- terminal status: `completed`, `failed`
- active status: `queued`, `running`
- timestamps
- `last_job_id`
- `output_count`

Derived runtime states should be computed in code, not stored as extra enums:

- `required`
- `skipped`
- `stale`
- `retryable`
- `blocked_by_dependency`

### Minimal schema recommendation

If crash-safe reclamation needs more than current state, add one nullable field:

- `lease_expires_at`

Why this is worth it:

- current `asset_processing` plus `jobs` can detect many stale cases
- but `jobs` has no heartbeat or `updated_at`
- a lease on the processing row gives the DAG executor a clean way to reclaim abandoned running nodes after worker death without redesigning the jobs system

If you want the absolute minimal schema path, this can be deferred and implemented later, but the design is cleaner with it.

## Node Evaluation Rules

Each node should answer:

1. Is this node applicable to this asset?
2. Which dependencies must be complete first?
3. Is the current output missing?
4. Is the current output stale for this node's version-sensitive rules?
5. Is there active work already queued or running?
6. Is force mode bypassing the usual completeness rules?

Examples:

- `tiny_thumbnail`
  - required for images and videos
  - completed if file exists
- `small_thumbnail`
  - required for videos and for image cases that should generate small inline/API variants
  - completed if file exists
- `image_preview`
  - applicable only to images with `has_large_preview`
  - completed if `large.webp` exists
- `video_preview`
  - applicable only to videos
  - completed if preview file exists and asset status is ready
- `clip_embedding`
  - completed only if both of these are true:
    - stored vector exists
    - `assets.search_model_id == current clip model id`
- `face_processing`
  - completed only for current face model id
  - stale if current default face model changed or recovery logic marks prior attempt abandoned
- `face_matching`
  - required only when requested by policy, not by every face-processing run

## Model Versioning

Model-sensitive nodes must include model identity in both state lookup and dedupe:

- CLIP uses `assets.search_model_id` and current default CLIP model id
- face processing uses `faces.face_model_id` and current default face model id

Never mix results across model versions.

The DAG definition should treat model version as part of the node instance identity:

- `clip_embedding(model_id=7)`
- `face_processing(model_id=3)`

`asset_processing.ai_model_id` already fits this model.

## Dedupe

The active `add-job-deduplication-and-queue-routing` change already introduces the right direction.

For DAG scheduling, the dedupe identity should be:

- `task + asset_id + model_id + params_hash`

Readable specializations remain useful:

- `preview:{asset_id}:{variant}`
- `clip:{asset_id}:{model_id}`
- `faces:{asset_id}:{model_id}:{auto_match}`
- `metadata:{asset_id}:{params_hash}`

No new dedupe table is required if dispatcher-backed dedupe stays authoritative.

`asset_processing` should answer "does this node appear complete or retryable?"

`jobs.dedup_key` should answer "is equivalent work already active?"

That is a clean separation.

## Parent Job Aggregation

Manual or batch jobs should remain parent orchestrators over many per-asset DAG runs.

Recommended aggregation model:

- parent job owns discovery, batching, and progress totals
- child jobs remain the actual per-asset node executions when user-visible granularity matters
- for bulk scheduling without one child per node, parent progress can also count asset-node plans created vs completed

Suggested rule:

- bulk scan stays a global/manual job with scan-specific counters
- CLIP/face/manual backfills keep parent job + child jobs
- the DAG service returns a deterministic plan summary for each asset so parent jobs know whether an asset was:
  - already satisfied
  - queued
  - completed inline
  - failed to enqueue

## Crash Recovery

Crash recovery should be node-centric and idempotent.

Proposed behavior:

- before running a node, executor claims it by setting `status=running`, `last_job_id`, `started_at`, and optional `lease_expires_at`
- on success, executor marks `completed`
- on failure, executor marks `failed`
- on reevaluation, if row is `queued` or `running` but:
  - referenced job is no longer active, or
  - lease expired
  - then node becomes `retryable`

This avoids stuck processing rows after worker death.

## Force vs Normal Reprocessing

Normal processing:

- runs only when outputs are missing, stale, or abandoned
- respects dependencies and dedupe

Forced processing:

- bypasses normal completeness checks for the targeted node
- still respects dependency correctness
- may delete and rebuild only disposable derived outputs
- must not destroy manual face decisions

Force should be targeted, not global by default.

Examples:

- force CLIP: regenerate vector for current model
- force face processing: rerun detection for current model, but preserve confirmed and excluded semantics
- force preview: rebuild disposable preview output

## Protecting Manual Face Corrections

This is a hard requirement.

Rules:

- confirmed faces must never be deleted by ordinary reruns
- excluded faces must remain excluded
- person assignments and manual confirmations remain authoritative
- force face processing may replace unconfirmed detections for the current model, but not confirmed manual decisions
- `face_matching` may only operate on eligible unmatched faces and should continue using existing assignment rules

This matches current behavior and should become an explicit DAG invariant.

## Upload and Scan Policy Differences

Upload and scan should share DAG semantics but not scheduling policy.

Upload policy:

- optimistic immediate readiness for one asset
- may do fast inline artifacts
- metadata entrypoint, normal priority for follow-up AI

Scan policy:

- discover many assets first
- schedule per-asset DAG work in batches
- prefer throughput-safe batch entry
- may skip creating child jobs for already-satisfied nodes

Same graph, different orchestration shell.

## Restore Policy

Restore should not blindly replay upload semantics.

Instead it should:

- restore DB asset state
- re-evaluate DAG nodes
- queue only missing or stale work
- run incremental face matching only if current-model faces already exist and matching is the only missing step

That keeps restore cheap and avoids unnecessary recomputation.

## Preview Policy

Preview remains demand-driven.

Use the same node state and dedupe rules:

- check node completion from durable output state
- if missing and inline path is allowed, generate inline and mark node completed
- otherwise enqueue the preview node with interactive or preview intent
- if equivalent preview work is already active, reuse it unless the dispatcher explicitly allows urgent duplicate behavior

## Migration Strategy

1. Add `processing_dag` service package with code-defined node definitions and policies.
2. Add a DAG state adapter over `asset_processing` and dispatcher-backed dedupe.
3. Migrate metadata job follow-up logic to the DAG executor first.
4. Migrate upload, scan, restore, and preview entrypoints to call DAG policies.
5. Migrate CLIP and face backfills to request DAG entry at model-sensitive nodes.
6. Refactor integrity repairs to reuse DAG node repair/requeue logic where applicable.
7. Keep existing worker task names initially; change scheduling before changing task bodies.

## Trade-offs

### Chosen

One shared per-asset DAG with policy overlays.

Why:

- centralizes dependency rules once
- keeps code understandable
- avoids separate DAG implementations for each workflow

### Rejected

Separate DAG per operation type.

Why rejected:

- duplicates node definitions and staleness rules
- makes model-version logic harder to keep aligned

### Rejected

Push global workflows like clustering into the per-asset DAG.

Why rejected:

- wrong scope
- complicates the graph with cross-asset orchestration that belongs in manual/global jobs

## Answers to the Exploration Questions

1. Follow-up enqueueing is scattered across upload/ingest, metadata jobs, scan, preview, restore, manual backfills, and integrity repair.
2. DAG entrypoints should be upload/ingest, scan-created or scan-reused assets, restore, preview requests, CLIP backfills, face backfills, and repair-triggered node reevaluation.
3. Formal DAG nodes should be `metadata_refresh`, `tiny_thumbnail`, `small_thumbnail`, `image_preview`, `video_preview`, `clip_embedding`, `face_processing`, and `face_matching`.
4. Per-asset: all listed DAG nodes. Batch/global: scan orchestration, clustering, storage rules, diagnostics, orphan cleanup, and parent-job aggregation.
5. Existing `asset_processing` is sufficient for coarse node state, with an optional minimal lease field recommended for abandoned-run recovery.
6. A new dedupe table is not needed if dispatcher dedupe stays authoritative.
7. Parent job progress should aggregate asset-plan outcomes and child job terminal states, not become DAG nodes themselves.
8. Crash recovery should reclaim `queued` or `running` nodes when the referenced job is inactive or the node lease expires.
9. Forced reprocessing should bypass completeness checks for targeted nodes but still preserve dependency correctness and manual face decisions.
10. Manual face corrections are protected by making confirmed, excluded, and manually assigned face state authoritative invariants.
11. Upload and scan should share node semantics while using different policy layers for batching, priority, and child-job creation.
12. Restore should re-evaluate nodes and queue only missing or stale work rather than replaying the full ingest path.
13. Preview requests should consult durable node state plus dispatcher dedupe so duplicate active work is reused unless urgent policy explicitly allows a duplicate.
