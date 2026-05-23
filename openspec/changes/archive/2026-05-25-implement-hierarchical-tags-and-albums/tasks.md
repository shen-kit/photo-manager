## 1. Schema and Models

- [x] 1.1 Add Alembic migration extending `tags` with `slug`, `is_album`, `cover_asset_id`, `created_at`, and `updated_at`, including backfill logic for existing rows.
- [x] 1.2 Update `backend/app/models.py` for extended tag schema, foreign key behavior, timestamps, and indexes consistent with current SQLModel patterns.
- [x] 1.3 Add or adjust tag-related constraints and indexes needed for ltree hierarchy queries, album projection, and cover lookups.

## 2. Tag and Album Domain Services

- [x] 2.1 Add shared tag repository/service methods for create, list, rename, move, delete, slug generation, sibling conflict checks, and subtree validation using `ltree`.
- [x] 2.2 Add cover-image validation helpers that accept direct or descendant asset membership for both tags and albums.
- [x] 2.3 Add delete flow support for `delete_children` defaulting to `false`, including conflict-style confirmation responses for branch deletes.
- [x] 2.4 Add response schemas for tag and album payloads, including `slug`, `path`, parent-path metadata, `is_album`, `cover_asset_id`, and timestamps.

## 3. Asset Tag Mutation Workflows

- [x] 3.1 Implement primary single-item asset-tag mutation flows with `POST /assets/{asset_id}/tags/{tag_id}` and `DELETE /assets/{asset_id}/tags/{tag_id}`.
- [x] 3.2 Implement batch add/remove flows for one or more tags across multiple assets with transaction-wide validation and idempotent behavior.
- [x] 3.3 Ensure asset detail responses continue to expose explicit tags only and preserve existing error-handling conventions.

## 4. Filtering and Retrieval

- [x] 4.1 Add shared descendant-aware tag filter query helpers with AND semantics across multiple selected tags.
- [x] 4.2 Extend asset browse, search, and timeline services plus cursor scope hashing to include descendant-aware tag filters without breaking pagination correctness.
- [x] 4.3 Add album detail/list retrieval on top of shared tag storage, returning only `is_album = true` tags and descendant-matched assets.
- [x] 4.4 Reuse existing browse grid and asset detail response shapes for tag/album asset payloads so dev frontend can exercise backend without new UI-specific models.

## 5. API Surface

- [x] 5.1 Add authenticated `tags` feature router for normal-tag CRUD, subtree/list queries, and cover updates.
- [x] 5.2 Add authenticated `albums` feature router that projects shared tag service behavior for `is_album = true` resources.
- [x] 5.3 Register new routers in `backend/app/api/v1/router.py` and wire request/response schemas using existing FastAPI patterns.

## 6. Verification and Docs

- [x] 6.1 Add or extend unittest coverage for tag hierarchy operations, delete-confirm behavior, explicit-only mutation semantics, descendant-aware filtering, cover validation, and cursor-scope behavior.
- [x] 6.2 Run `python -m compileall backend/app backend/worker.py` after implementation.
- [x] 6.3 Manually verify tag and album CRUD, branch-delete confirmation flow, single add/remove, batch tagging, descendant-aware filtering, cover validation, and reused grid/detail payloads through `/docs` or API calls.
