## Context

Current asset deletion is soft-delete only: `AssetService.delete_asset` sets `deleted_at` and runs people reconciliation. Trash APIs already expose list, detail, and restore operations through `TrashService`. Media paths are constrained by existing helpers such as `master_path_to_source_path` and `processed_asset_dir`, and many dependent records already cascade from `assets.id` at the database level.

This change must preserve that architecture: trash remains the only boundary for irreversible deletion, service orchestration stays in `TrashService`, SQL stays in repositories, and path confinement stays in shared media helpers.

## Goals / Non-Goals

**Goals:**
- Support permanent deletion of one trashed asset, many selected trashed assets, and all trashed assets.
- Remove original files and processed derivatives from disk before final DB deletion.
- Guarantee active assets can never be permanently deleted through these flows.
- Reuse existing repository/service/test patterns and preserve straightforward FastAPI contracts.
- Provide deterministic partial-failure reporting for bulk operations.

**Non-Goals:**
- No automatic age-based trash expiry.
- No background purge jobs in this change.
- No UI work.
- No changes to soft-delete semantics outside trash.
- No deletion of files outside media roots, even if bad data exists in the database.

## Decisions

### Permanent delete lives in trash service, not asset service

Soft delete remains in `AssetService`; irreversible deletion belongs to `TrashService` because only trashed assets are eligible. This keeps lifecycle stages explicit:

```text
active -> soft deleted (trash) -> permanently deleted
```

Alternative considered: add purge methods to `AssetService`. Rejected because it blurs soft-delete and irreversible-delete responsibilities.

### API surface mirrors restore patterns

Add three trash endpoints:

- `DELETE /trash/assets/{asset_id}` for single purge
- `POST /trash/assets/delete` for bulk purge by `asset_ids`
- `DELETE /trash/assets` for empty trash

This keeps destructive operations under `/trash`, matches current single-vs-bulk restore structure, and follows the repo’s existing delete-all route style.

### Hard guard: only trashed assets may be purged

Every purge path begins by loading assets with `deleted_at IS NOT NULL`. If an asset is active or missing, service returns not-found/failed status and performs no file deletion. Empty-trash queries only scan deleted assets.

This rule must live in repository/service code, not only in HTTP handlers, so future call sites inherit the same safety barrier.

### Delete files first, delete DB row second

Purge order:

1. Resolve safe delete targets for original and processed files.
2. Remove files/directories.
3. Delete asset row from DB.

Rationale: if file deletion fails, keep DB row so asset remains visible in trash and retryable. If DB deletion happened first and file deletion failed later, storage would leak while discoverability disappears.

Trade-off: DB row may remain while some files are already gone. This is acceptable because restore already handles missing originals as a conflict, and retrying purge remains safe.

### File deletion must stay within media roots

Original file deletion uses existing `master_path_to_source_path`, which already rejects path escape. Processed cleanup uses `processed_asset_dir(asset.id)` and recursively removes only that asset directory. If future purge logic touches `crop_path` or similar per-file fields, each path must be resolved against processed root before deletion.

Missing files are treated as non-fatal for already-computed safe targets where absence simply means nothing left to reclaim. Invalid escaped paths are fatal and block DB deletion for that asset.

### Rely on existing FK cascades for dependent database cleanup

Deleting the `Asset` row should cascade dependent rows such as faces, asset-processing rows, and asset-tag joins. `cover_asset_id` on tags already becomes `NULL`. Because people cleanup already happens during soft delete, purge should not add a second people-maintenance pass unless implementation reveals a gap.

Alternative considered: explicit manual deletion of every child table. Rejected because it duplicates existing DB constraints and increases drift risk.

### Bulk purge uses partial-success response shape

Bulk purge should deduplicate asset IDs like restore does, attempt each asset independently, and return counts plus per-item failures. One bad asset must not block other eligible assets.

Empty-trash can return aggregate counts only because caller is asking to purge whole set, not track specific IDs.

## Architecture

### Service responsibilities

- `TrashService`
  - orchestrates eligibility checks
  - deduplicates IDs
  - builds per-asset purge plan
  - executes safe file deletion
  - invokes repository deletion
  - formats success/failure aggregates

- `AssetRepository`
  - fetch deleted assets for single/bulk/all-trash flows
  - delete asset rows
  - count/list deleted assets as today

- Shared media helper or trash-local helper
  - resolve original path via existing helper
  - build processed asset directory path
  - recursively remove processed directory
  - validate any file path remains under expected root

### Purge flow

```text
req
 -> trash API
 -> TrashService
    -> get deleted asset(s)
    -> build safe paths
    -> delete original file
    -> delete processed dir
    -> delete asset row
 -> response
```

### Response modeling

Single purge:
- `204 No Content`

Bulk purge:
- request: `asset_ids`
- response: requested / deleted / failed + failure list

Empty trash:
- response: deleted count, failed count, failure list if desired for consistency

If implementation simplicity is better, bulk and empty-trash may share a common summary schema with optional `requested`.

## Risks / Trade-offs

- Partial purge can leave DB row with some missing files.
  - Mitigation: file-first ordering, idempotent retry behavior, clear failure reporting.
- Invalid `master_path` data could point outside media root.
  - Mitigation: reuse existing constrained path resolver and block purge on invalid path.
- Recursive processed-dir deletion could accidentally over-delete if path construction is wrong.
  - Mitigation: derive only from `processed_asset_dir(asset.id)` and validate under processed root.
- Empty-trash can be expensive with many assets.
  - Mitigation: iterate deleted assets in batches if needed, but keep first implementation simple unless volume demands batching.

## Edge Cases and Failure Modes

- Active asset ID passed to purge endpoint: reject / mark failed; do nothing on disk.
- Duplicate asset IDs in bulk purge: deduplicate before work.
- Original file already missing: allow purge to continue if path is valid; goal is final cleanup.
- Processed directory missing: allow purge to continue.
- Invalid escaped source path: fail that asset; keep DB row.
- DB deletion failure after file deletion: report failure; asset remains in trash row if transaction not committed.
- Empty trash when nothing deleted: return zero counts, succeed.

## Test Strategy

- Service tests for single purge success, active-asset rejection, duplicate-id bulk handling, partial failures, and empty-trash aggregation.
- Service tests for invalid `master_path` safety guard and missing-file idempotence.
- API tests for new single, bulk, and empty-trash endpoints plus response shapes.
- Verification that purge calls repository deletion only for trashed assets.
- Syntax check and targeted unittest runs for trash service/API tests during implementation.
