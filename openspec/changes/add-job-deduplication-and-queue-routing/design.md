## Context

Current backend enqueues all ARQ tasks through `app/services/jobs/queue.py` into one Redis queue (`arq:queue`). Some call sites already do narrow dedupe in application code, such as preview jobs by `related_asset_id` and manual jobs by root `job_key`, but there is no central policy for semantic dedupe, queue routing, or force-bypass behavior.

This means user-triggered work, such as opening an asset preview, competes directly with full-library backfills for CLIP, face processing, thumbnails, previews, and maintenance jobs. The target host is a Dell Optiplex, so responsiveness matters more than peak throughput.

## Goals / Non-Goals

**Goals:**
- Introduce a central `JobDispatcher`-style enqueue layer that owns semantic dedupe, queue routing, and enqueue metadata.
- Use global active-job dedupe across queues for equivalent semantic work.
- Allow urgent duplicates to be enqueued when user intent requires faster service than an already-queued background job.
- Route jobs into dedicated ARQ queues and split workers into `worker-fast` and `worker-batch`.
- Keep heavy work conservative through worker concurrency and per-job-type semaphores.
- Preserve existing task implementations where practical by changing scheduling around them rather than rewriting every task body.

**Non-Goals:**
- No attempt to maximize total batch throughput.
- No dynamic queue autoscaling or cluster-wide scheduling heuristics.
- No priority system inside one Redis queue.
- No job preemption or migration of already-running work between queues in the first version.
- No replacement of current ARQ stack with Celery, Dramatiq, or another queue system.

## Decisions

### Add dispatcher-owned semantic dedupe keys

Each enqueued job will compute a deterministic semantic dedupe key based on task identity and relevant inputs. Default formula is `task + asset_id + model_id + params_hash`, with readable specializations for common asset work:
- `preview:{asset_id}`
- `clip:{asset_id}:{model_id}`
- `faces:{asset_id}:{model_id}:{auto_match}`
- `metadata:{asset_id}:{params_hash}`

For large batch or maintenance payloads, readable prefixes plus a stable hash are acceptable.

Alternative considered: reuse `job_key` and `related_asset_id`. Rejected because those fields are too coarse and do not distinguish model versions or parameter-sensitive jobs.

### Global dedupe across queues, but urgent duplicates may bypass it

Normal enqueue flow will search active jobs globally by semantic dedupe key, regardless of queue, and avoid enqueuing duplicates. However, user-triggered urgent work may explicitly request a duplicate enqueue when the existing active work sits in a lower-priority lane, such as:
- preview queued for scan/backfill
- later user opens asset and needs prompt preview generation

This duplicate enqueue is deliberate, not accidental, and should be explicit at call sites through dispatcher intent/options. `force=true` remains a separate, stronger bypass for jobs that intentionally ignore dedupe entirely.

Alternative considered: always reuse global duplicate. Rejected because it preserves correctness but not responsiveness when urgent interactive work is stuck behind background lanes.

### Store queue and dedupe metadata on `jobs`

The `jobs` table should track queue-routing and dedupe metadata explicitly, likely including:
- `queue_name`
- `dedup_key`
- `intent`
- optional `params_hash`

This makes dedupe queries, operator debugging, and future UI inspection straightforward.

Alternative considered: derive all of this from `parameters` JSON only. Rejected because JSON-only lookups are harder to query consistently and harder to audit operationally.

### Route by intent, not by task name alone

Same underlying task function may need different queues depending on why it was requested:
- user-requested preview → `interactive`
- normal preview generation → `preview`
- full-library preview repair → `backfill`

Dispatcher will therefore accept explicit intent and map `(task, intent)` to queue and dedupe policy.

Alternative considered: one task maps to one queue always. Rejected because it cannot express urgent interactive overrides cleanly.

### Use multiple ARQ queues and two worker roles

Queue set:
- `interactive`
- `metadata`
- `preview`
- `ai`
- `backfill`
- `maintenance`

Worker roles:
- `worker-fast`: consumes `interactive`, `metadata`, `preview`
- `worker-batch`: consumes `ai`, `backfill`, `maintenance`

Both workers use same Docker image and codebase. Queue subscriptions and concurrency come from environment variables.

Alternative considered: add numeric priority inside current single queue. Rejected because ARQ queue order would still leave all work sharing one contention lane, which misses core responsiveness goal.

### Keep conservative worker-level concurrency and add per-job-type semaphores

Starting point:
- `worker-fast` concurrency: 1–2
- `worker-batch` concurrency: 1

Additional execution guards:
- video preview concurrency: 1
- CLIP concurrency: 1
- face detection concurrency: 1
- face clustering concurrency: 1
- scan concurrency: 1

Per-job-type semaphores remain useful even with queue separation because one worker may still have more than one task slot.

Alternative considered: worker-level concurrency only. Rejected because mixed heavy functions on same worker could still saturate CPU/RAM unpredictably.

### Keep inline image preview path

Current preview service can generate some small image previews inline. That path helps user responsiveness and does not conflict with queue separation goals, so it should remain.

Alternative considered: force all preview work through queues for consistency. Rejected because it adds latency to a path that already behaves well.

### Migrate existing enqueue helpers into thin dispatcher wrappers

Current enqueue helpers are widely referenced. Instead of removing them abruptly, convert them into thin wrappers over dispatcher so call sites can migrate incrementally while preserving readable task-specific entrypoints.

Alternative considered: replace all enqueue calls directly with dispatcher calls in one sweep. Rejected because it increases rollout risk and diff size unnecessarily.

## Risks / Trade-offs

- [Urgent duplicate work increases total compute] → Mitigation: allow only explicit urgent bypasses, keep them narrow to interactive paths like on-demand preview.
- [Dedupe key too coarse suppresses valid work] → Mitigation: include model id and parameter-sensitive fields in semantic keys; document per-task key rules.
- [Dedupe key too fine causes accidental duplicate work] → Mitigation: centralize key generation in dispatcher instead of rebuilding keys ad hoc in each service.
- [Queue split introduces operational complexity] → Mitigation: keep only two worker roles initially, both from same Docker image and same code.
- [Heavy tasks still contend inside one worker role] → Mitigation: add per-job-type semaphores and start with low worker concurrency.
- [Migration may leave mixed old/new enqueue behavior temporarily] → Mitigation: convert legacy enqueue helpers into dispatcher-backed wrappers early in rollout.

## Migration Plan

1. Add `jobs` table fields needed for queue/dedupe metadata.
2. Introduce `JobDispatcher` and migrate current enqueue helpers to call through it.
3. Define queue names, intent enums, and per-task dedupe-key builders.
4. Update preview, metadata, embedding, face, trash, and manual-job flows to pass intent and bypass options.
5. Split worker settings so queue subscriptions and concurrency come from environment variables.
6. Update `docker-compose.yml` to replace `worker` with `worker-fast` and `worker-batch`.
7. Add per-job-type semaphores for conservative heavy-work serialization.
8. Validate interactively: preview responsiveness under backfill load, dedupe behavior, and force-bypass behavior.
9. Rollback path: revert worker topology to one worker role and route all queues back to legacy single-queue settings after disabling new dispatcher fields.

## Open Questions

- Whether urgent duplicate job rows should explicitly reference the active lower-priority job they are bypassing for easier observability.
    - Answer: Yes, if it doesn't involve changing the database schema and is clear what the job id is for. If not, do not implement this.
- Whether ARQ queue subscription order should bias `interactive` ahead of `metadata` and `preview` inside `worker-fast`, or whether separation plus low concurrency is sufficient.
    - Answer: Yes, but only if it is clean to implement and doesn't try to bypass how arq and redis are designed to work.
- Whether maintenance jobs that currently execute inside API-owned executors should also emit dispatcher metadata for uniform observability even if not queued through ARQ.
    - Answer: No
