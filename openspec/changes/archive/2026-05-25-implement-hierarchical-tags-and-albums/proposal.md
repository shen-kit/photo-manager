## Why

This self-hosted photo manager already has `tags`, `asset_tags`, and PostgreSQL `ltree`, but it does not expose the hierarchy as a first-class product feature. Users cannot yet manage nested tags, treat parent tags as descendant-aware filters, batch-tag assets, or model albums without inventing a second overlapping taxonomy system.

## What Changes

- Extend `tags` so one hierarchy supports both normal tags and albums by adding album metadata and lifecycle fields to the existing table.
- Add hierarchical tag and album CRUD flows backed by `ltree`, including slug/path generation that separates user-facing names from ltree-safe path segments.
- Add explicit asset-tag APIs for single-tag add/remove plus batch tagging across multiple assets; store only explicit assignments in `asset_tags`.
- Add descendant-aware asset filtering so selecting parent tags or albums matches assets tagged with any descendant, with AND semantics across multiple selected filters.
- Add tag and album cover image support using `cover_asset_id`, validated against direct or descendant asset membership.
- Extend browse/search/timeline planning so new filters preserve existing cursor pagination and service conventions.

## Capabilities

### New Capabilities
- `hierarchical-tags`: Manage nested tags, explicit asset tag assignments, and descendant-aware filtering.
- `albums`: Expose album workflows as `tags` with `is_album = true`, including cover images and album-focused browse flows.

### Modified Capabilities
- None.

## Impact

- Affected code: `backend/app/models.py`; Alembic migrations under `backend/alembic/versions/`; new or extended routers under `backend/app/api/v1/features/`; shared tag/filter logic in `backend/app/services/`; tests under `backend/tests/`.
- Affected APIs: new tag and album CRUD endpoints; single-asset tag add/remove endpoints; batch tagging endpoints; tag-aware browse/search/timeline filters.
- Affected schema: `tags` table changes for `slug`, `is_album`, `cover_asset_id`, timestamps, indexes, and constraints; no separate `albums` table.
- Affected behavior: parent tag filters will match descendant explicit tags without storing inherited joins; people remain separate entities and are not represented as tags.
