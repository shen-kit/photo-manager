## Why

The backend currently enqueues all ARQ work into one queue, so full-library backfills can delay user-triggered previews and other interactive actions. Job deduplication is also inconsistent today, which leads to avoidable duplicate work for some job types while still lacking a clean way to prioritize urgent user actions over background throughput.

## What Changes

- Add a central job dispatching layer that owns queue routing, deduplication, and force-bypass behavior for worker-enqueued jobs.
- Introduce deterministic dedupe keys for asset-specific and batch/background jobs, with global active-job dedupe across queues.
- Allow `force=true` to bypass dedupe for supported jobs.
- Route the same semantic task to different queues based on intent, such as interactive preview requests versus full-library preview backfills.
- Replace the single generic ARQ worker topology with queue-specific worker roles:
  - `worker-fast` for `interactive`, `metadata`, and `preview`
  - `worker-batch` for `ai`, `backfill`, and `maintenance`
- Add conservative concurrency controls and per-job-type execution limits so heavy work does not swamp the Dell Optiplex host.

## Capabilities

### New Capabilities
- `job-dispatching`: Centralized enqueue policy with global dedupe, force bypass, queue routing, and enqueue metadata.
- `worker-queue-topology`: Queue-specific worker roles, routing rules, and conservative concurrency/serialization for heavy job classes.

### Modified Capabilities
- None.

## Impact

- Affected code: `backend/app/services/jobs/`, enqueue call sites in asset, face, embedding, trash, and manual job services, plus worker task/settings modules under `backend/worker/`.
- Affected infrastructure: `docker-compose.yml` worker services and worker environment configuration.
- Affected schema: likely `jobs` table changes for dedupe and queue metadata.
- Affected behavior: duplicate active work will be suppressed globally except when explicitly bypassed, while urgent user-triggered work can be enqueued separately from backfill lanes.
