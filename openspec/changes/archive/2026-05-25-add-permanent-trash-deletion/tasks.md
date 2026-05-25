## 1. Trash Purge Domain

- [x] 1.1 Extend trash schemas with request/response models for bulk purge and empty-trash summaries.
- [x] 1.2 Add `TrashService` methods for single purge, bulk purge, and empty trash, reusing existing deleted-asset lookup and ID dedup patterns.
- [x] 1.3 Add safe file-removal helpers for originals and processed asset directories that enforce media-root confinement.

## 2. Repository and Storage Integration

- [x] 2.1 Extend `AssetRepository` with helpers to fetch deleted assets for bulk/all-trash purge and to delete asset rows.
- [x] 2.2 Ensure repository-level deletion relies on existing FK cascade behavior instead of duplicating child-table cleanup.
- [x] 2.3 Define and document failure behavior for invalid paths, missing files, and post-file-delete DB errors.

## 3. Trash API

- [x] 3.1 Add `DELETE /trash/assets/{asset_id}` for single permanent delete.
- [x] 3.2 Add `POST /trash/assets/delete` for bulk permanent delete by `asset_ids`.
- [x] 3.3 Add `DELETE /trash/assets` for emptying trash, and register any new response models in the trash router.

## 4. Verification

- [x] 4.1 Extend trash service tests for purge success, safety guards, partial failures, and empty-trash behavior.
- [x] 4.2 Extend trash API tests for single, bulk, and empty-trash endpoints.
- [x] 4.3 Run `python -m compileall backend/app backend/worker.py` and targeted trash unittests after implementation.
