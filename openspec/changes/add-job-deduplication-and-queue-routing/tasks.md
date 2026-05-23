## 1. Job Metadata and Dispatcher Foundation

- [x] 1.1 Add DB migration and model updates for job queue/dedupe metadata such as `queue_name`, `dedup_key`, `intent`, and any required hash fields or indexes.
- [x] 1.2 Add central `JobDispatcher`-style service that computes semantic dedupe keys, chooses queues from task intent, and supports `force` bypass plus explicit urgent duplicate enqueue.
- [x] 1.3 Convert existing enqueue helper functions in `backend/app/services/jobs/queue.py` into dispatcher-backed wrappers so current call sites can migrate incrementally.

## 2. Dedupe and Intent Routing

- [x] 2.1 Implement deterministic dedupe-key builders for preview, metadata, CLIP, face, batch, and maintenance job classes.
- [x] 2.2 Add global active-job lookup by semantic dedupe key across queues and define reuse-versus-duplicate behavior for urgent interactive requests.
- [x] 2.3 Update preview, metadata, embedding, face, trash, and manual-job scheduling flows to pass explicit intent and dedupe-bypass options through dispatcher.

## 3. Worker Queue Topology

- [x] 3.1 Update worker settings so queue subscriptions and base concurrency are driven by environment variables rather than one hardcoded queue.
- [x] 3.2 Add queue definitions for `interactive`, `metadata`, `preview`, `ai`, `backfill`, and `maintenance`.
- [x] 3.3 Update `docker-compose.yml` to replace the generic worker with `worker-fast` and `worker-batch` using the same image and different queue/concurrency env config.

## 4. Concurrency Controls

- [x] 4.1 Add conservative default worker concurrency for `worker-fast` and `worker-batch`.
- [x] 4.2 Add per-job-type semaphores or equivalent execution guards for video preview, CLIP, face detection, face clustering, scan, and other heavy work classes.
- [x] 4.3 Ensure current inline image preview generation remains intact and does not regress under the new dispatching model.

## 5. Verification

- [x] 5.1 Add or extend tests for dedupe-key generation, global active-job dedupe, `force=true` bypass, and urgent duplicate enqueue behavior.
- [x] 5.2 Add or extend tests for queue routing by intent, worker configuration parsing, and conservative concurrency guards.
- [ ] 5.3 Manually verify that user-triggered preview work remains responsive while backfill jobs are active, and that duplicate active work is suppressed except for explicit urgent or forced bypasses.
