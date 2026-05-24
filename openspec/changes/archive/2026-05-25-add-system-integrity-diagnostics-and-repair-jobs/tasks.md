## 1. Persistence and Domain Foundation

- [x] 1.1 Add database schema and models for `diagnostic_runs` and `diagnostic_run_items`, including indexes needed for run lookups, paging, and retention cleanup.
- [x] 1.2 Create a `system_integrity` service/repository/schema module structure for code-defined diagnostic definitions, run persistence, and paginated item retrieval.
- [x] 1.3 Add retention logic that keeps only the last three runs per diagnostic and deletes older linked item rows.

## 2. Diagnostic Execution Framework

- [x] 2.1 Add dispatcher-backed diagnostic job keys with a `diagnostic:` prefix and wire them into worker task registration.
- [x] 2.2 Implement shared diagnostic execution flow for creating queued runs, marking run lifecycle state, storing summary data, and persisting per-item findings.
- [x] 2.3 Add API endpoints for listing diagnostics, starting a run, viewing latest or specific runs, and paging through run items.

## 3. Diagnostic Implementations

- [x] 3.1 Implement `check_originals_exist` as a detect-only diagnostic that records missing or invalid original-file findings.
- [x] 3.2 Implement `check_asset_derivatives` as a combined derivative diagnostic with subtype counts for `tiny`, `small`, `large`, and `video_preview`.
- [x] 3.3 Implement `check_clip_embeddings` using current default model semantics for missing, outdated, and stale tracker cases.
- [x] 3.4 Implement `check_face_processing` using current default model semantics for missing, outdated, and stale tracker cases.
- [x] 3.5 Implement `check_original_files_without_db_assets` and `check_processed_files_without_db_assets` as separate diagnostics.
- [x] 3.6 Implement `check_people_without_active_faces` using current person/face activity rules.

## 4. Repair Integration

- [x] 4.1 Add repair-launch API flow that creates a repair job from a persisted diagnostic run and blocks repair for detect-only diagnostics.
- [x] 4.2 Reuse or extend existing repair jobs so derivative, CLIP, and face repairs consume persisted snapshot scope with live per-item revalidation.
- [x] 4.3 Add repair support for deleting people with no active faces after revalidation against the current database state.
- [x] 4.4 Record repair linkage on diagnostic runs and return repair progress/status through existing job detail surfaces.

## 5. Verification

- [x] 5.1 Add tests for run creation, run completion, item persistence, and paginated item retrieval.
- [x] 5.2 Add tests for retention cleanup, ensuring only the newest three runs per diagnostic remain.
- [x] 5.3 Add tests for repair launch behavior, including snapshot-scoped revalidation, detect-only diagnostics, and people cleanup.
- [x] 5.4 Run targeted verification for large result sets and a fast syntax pass such as `python -m compileall backend/app backend/worker.py`.
