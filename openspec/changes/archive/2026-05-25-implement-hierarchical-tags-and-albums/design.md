## Context

Codebase already has `Tag` and `AssetTag` models, `ltree` enabled in Alembic, feature-first FastAPI routers, SQLModel models, service/repository boundaries, and unittest-based service tests. Asset browse and search flows already rely on filtered subqueries plus cursor scopes, so tag filtering must compose with those patterns rather than introduce ad hoc pagination.

Albums will not be a new table. They are specialized tags with `is_album = true`. Normal tags use `is_album = false`. People remain separate and must not be folded into tags. Explicit joins in `asset_tags` stay authoritative; inherited parent matches are query-time behavior only.

## Goals / Non-Goals

**Goals:**
- Expose first-class APIs for hierarchical tag and album CRUD using existing `tags` table.
- Preserve explicit tagging semantics: only manually assigned tags are stored in `asset_tags`.
- Support descendant-aware filtering for browse/search/timeline with AND semantics across multiple selected tags.
- Support both single-asset tag add/remove and multi-asset batch add/remove workflows.
- Add cover images for tags and albums with robust validation.
- Preserve current project conventions for routers, services, repositories, Alembic, SQLModel, tests, and HTTP error handling.

**Non-Goals:**
- No automatic tag generation from AI, EXIF, or folders.
- No automatic parent-tag materialization in `asset_tags`.
- No separate album membership table.
- No conversion of people into tags.
- No smart albums, sharing, permissions, or UI implementation in this change.

## Decisions

### Keep one authoritative hierarchy in `tags`

`tags.path` remains source of truth for hierarchy. We will not add a separate `albums` table or duplicate hierarchy state in `parent_id`. Instead, albums are tags flagged with `is_album = true`. This keeps one ancestry model, one join table, one descendant query strategy, and one service stack.

Alternative considered: separate `albums` table plus membership table. Rejected because it duplicates asset grouping semantics already available through tags and complicates cross-filtering.

### Add `slug`, `is_album`, `cover_asset_id`, `created_at`, and `updated_at` to `tags`

- `slug`: stored ltree-safe leaf segment used to build `path`
- `is_album`: distinguishes album-focused tags from normal tags
- `cover_asset_id`: nullable FK to `assets.id`, `ON DELETE SET NULL`
- `created_at` / `updated_at`: align with existing model patterns and support auditability

`name` remains user-facing display text and may contain spaces, punctuation, and casing unsuitable for ltree. `slug` is generated from `name` unless explicitly provided, normalized to lowercase snake-like segments compatible with `ltree`. `path` becomes parent path plus slug.

Alternative considered: derive slug transiently from `name` and store only `path`. Rejected because rename/move flows, conflict reporting, and stable editing are cleaner when leaf slug is explicit.

### Do not add `parent_id`

`path` already captures ancestry and supports subtree queries efficiently with `ltree`. Adding `parent_id` would introduce duplicated hierarchy state, more migration complexity, and more failure modes during subtree moves.

Alternative considered: add `parent_id` for simpler joins. Rejected because service methods can derive parent from `subpath(path, 0, -1)` and descendants from ltree operators without storing duplicate state.

### Allow duplicate display names across different parents, reject slug collisions within same parent

Different branches may contain same display name or same slug because `path` remains unique globally by full ancestry. Within same parent, resulting `path` must be unique. Service validation will reject sibling conflicts before commit and still rely on DB uniqueness for race safety.

Alternative considered: globally unique names or slugs. Rejected because hierarchical taxonomies need repeated labels like `Favorites` or `Cover`.

### Single-item relation endpoints are primary; batch endpoints supplement them

Primary asset-tag APIs:
- `POST /assets/{asset_id}/tags/{tag_id}`
- `DELETE /assets/{asset_id}/tags/{tag_id}`

Batch APIs:
- `POST /assets/tags:batch-add`
- `POST /assets/tags:batch-remove`

These endpoints are idempotent. They add or remove explicit joins only. They do not materialize parent tags and do not use replace-all semantics as primary API.

Alternative considered: `PUT` replace-all tags on asset. Rejected because user requirements prefer additive/removal semantics and explicit relationship preservation.

### Add dedicated `tags` and `albums` routers over shared service layer

Expose `/tags` for normal tags and `/albums` for `is_album = true` tags, but implement both through shared tag repository/service code. This keeps user-facing API readable without splitting persistence.

Alternative considered: one `/tags` API with `is_album` query flags only. Rejected because album workflows deserve explicit endpoints even though storage is shared.

### Delete flow uses explicit `delete_children` confirmation

Delete requests will accept `delete_children`, defaulting to `false`. If client attempts to delete tag or album with descendants while `delete_children=false`, API should return a conflict-style response with machine-readable detail that frontend can use to show confirmation dialog. If user confirms, client retries with `delete_children=true`, and service deletes subtree plus matching `asset_tags` joins in one transaction.

Alternative considered: always require separate preview endpoint before delete. Rejected because one delete endpoint with confirmable conflict response is simpler for backend and sufficient for current dev frontend.

### Cover validation uses descendant-aware membership checks

When setting `cover_asset_id`, service must verify asset is explicitly tagged with target tag or with any descendant of target tag. This matches user expectation that parent tags and albums represent full subtree membership without backfilling joins.

Alternative considered: require direct membership only. Rejected because parent tag and album cover selection would fail for common nested-only tagging workflows.

### Descendant-aware filtering uses grouped join/having strategy

For selected filter tags `[T1, T2, ...]`, query strategy:
1. Resolve selected tag ids to paths.
2. Join `asset_tags` to assigned tags.
3. Count distinct selected filters matched by `assigned_tag.path <@ selected_tag.path`.
4. Keep assets where matched selected-filter count equals number of requested filters.

This yields AND semantics across filters while allowing descendant matches per selected tag. Explicit joins remain sparse because parents are not materialized.

Alternative considered: OR semantics or recursive join expansion in application memory. Rejected because requirements specify AND by default and DB-side grouping is more robust.

### Pagination correctness stays filter-scoped

Browse/search/timeline services already encode filter scope into cursors. Tag filters must be added to those scope hashes and applied in `matching_assets` subqueries before sorting/limiting. This preserves stable pagination and prevents cursor reuse across incompatible filter sets.

Alternative considered: post-filter current page in application code. Rejected because it breaks counts, cursor stability, and page density.

### Service boundaries

- `TagRepository`: low-level tag CRUD, path queries, subtree updates, cover validation helpers
- `TagService`: validation, slug generation, rename/move/delete semantics, album projection rules
- `AssetTagService` or extension of `AssetService`: single add/remove plus batch tagging commands
- `AssetBrowseService` / `SearchService` / timeline service: consume shared tag-filter query helper

This follows current repository + service split and avoids putting hierarchy logic inside routers.

## Risks / Trade-offs

- Subtree rename/move updates many rows → Mitigation: do subtree updates in one transaction with set-based SQL and `ltree` indexes.
- Shared hierarchy for tags and albums can blur semantics → Mitigation: keep `is_album` explicit in schema and API projection, document that storage is shared but endpoints are filtered.
- Slug normalization can surprise users when names contain unsupported characters → Mitigation: define deterministic slug rules, expose resulting slug/path in responses, reject empty or reserved slugs.
- Batch tagging can partially fail if validation is weak → Mitigation: validate all tag ids and asset ids before mutation, execute transactionally, return deterministic counts.
- Descendant-aware filtering can regress browse/search performance → Mitigation: use DB-side joins/grouping, add indexes, and keep cursor scope tied to tag filters.
- Cover assets can become invalid after tag removal or subtree moves → Mitigation: validate on write and define fallback behavior for stale covers during future tag edits.

## Migration Plan

1. Create Alembic migration that adds `slug`, `is_album`, `cover_asset_id`, `created_at`, and `updated_at` to `tags`.
2. Backfill existing rows:
   - `slug` from leaf path segment
   - `is_album = false`
   - timestamps from `now()`
3. Add FK and indexes:
   - keep `path` unique and gist-indexed
   - add btree index on `is_album`
   - add btree index on `cover_asset_id`
   - consider composite index on `(is_album, path)` only if query plans need it
4. Deploy shared tag services and routers.
5. Extend asset browse/search/timeline filters to include descendant-aware tag matching.
6. Rollback path: remove app usage first, then revert migration if no new fields are relied on.

### Album and tag asset payloads reuse existing grid/detail shapes

For current development frontend, album detail and tag-filtered asset views should reuse existing browse grid item and asset detail response shapes rather than inventing new UI-specific payloads. This keeps backend surface smaller and aligns with current testing-focused frontend. If later production UI needs different projections, that can be a follow-up change.

## Edge Cases and Failure Modes

- Creating or renaming tag yields empty slug after normalization → reject with `422`.
- Moving tag under itself or its descendant → reject with `422`.
- Creating sibling whose normalized slug collides with existing sibling slug → reject with `409` or project-standard validation error.
- Deleting non-leaf tag without `delete_children=true` → return conflict-style response with enough metadata for confirmation UX.
- Removing explicit child tag leaves explicit parent tag intact; removing explicit parent leaves explicit child intact.
- Setting cover asset that belongs only through unrelated tag branch → reject.
- Filtering by missing tag ids → reject rather than silently drop, so AND semantics stay predictable.
- Batch add where some joins already exist → no-op for those rows, still succeed.
- Batch remove where some joins do not exist → no-op for those rows, still succeed.
- Cursor reused with different tag filters → reject via scope mismatch, consistent with current browse/search cursor handling.

## Test Strategy

- Add unit tests for slug normalization, sibling conflict checks, rename/move subtree updates, delete-confirm guards, and cover validation.
- Add service tests for single add/remove and batch add/remove preserving explicit-only semantics.
- Add repository or service tests for descendant-aware AND filtering across one or more selected tags.
- Extend browse/search/timeline tests to cover cursor scope with tag filters, pagination stability, and reuse of existing asset grid/detail payload shapes in tag/album retrieval.
- Add migration test coverage or at minimum manual verification for backfilled tag fields and FK/index creation.
