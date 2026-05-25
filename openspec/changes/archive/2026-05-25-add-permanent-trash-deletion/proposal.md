## Why

Trash currently supports soft delete and restore, but not irreversible cleanup. Trashed assets continue consuming disk because original media and generated derivatives remain on disk, and the database continues retaining asset rows plus dependent records. Users need a safe way to reclaim storage without risking active assets.

## What Changes

- Add permanent-delete flows under trash for a single asset, multiple selected assets, and emptying the entire trash.
- Delete both original media files and generated processed files for purged assets, then remove the asset rows and dependent database records.
- Enforce hard safety rules so only assets already in trash can be permanently deleted.
- Reuse existing trash, asset repository, media path, and people-maintenance patterns rather than introducing a parallel deletion stack.
- Add automated coverage for success, partial-failure, and safety-guard scenarios.

## Capabilities

### New Capabilities
- `trash-purge`: Permanently delete trashed assets from disk and database, individually, in bulk, or by emptying the trash.

### Modified Capabilities
- None.

## Impact

- Affected code: `backend/app/api/v1/features/trash.py`; `backend/app/services/trash/`; `backend/app/services/assets/repository.py`; shared media-path helpers under `backend/app/services/assets/`; tests under `backend/tests/`.
- Affected APIs: new trash purge endpoints for single item, bulk delete, and empty-trash operations.
- Affected behavior: permanently deleted assets lose originals, generated previews/thumbnails, and related DB rows; active assets remain protected.
- Affected storage: disk space reclaimed from `storage/originals/` and `storage/processed/` for purged assets only.
