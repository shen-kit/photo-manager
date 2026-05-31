## Context

The repository contains a FastAPI backend with a complete committed OpenAPI schema and a placeholder Flutter project in `mobile/`. The backend exposes bearer access JWTs plus a rotating refresh-token cookie, cursor-based active asset browsing, timeline month/day buckets, static processed/original media routes, on-demand preview ensure, hierarchical tags/albums, semantic search, people/faces, jobs, notifications, diagnostics, trash, and uploads.

Mobile must be performant on large self-hosted libraries and robust when media already exists on the device. Android is the first-class target, but implementation should keep platform abstractions Flutter-compatible where possible.

## Goals / Non-Goals

**Goals:**
- Implement a complete maintainable Flutter app that consumes current backend APIs exactly as described by `backend/openapi-schema.json`.
- Keep app architecture feature-based with clean API, repository, controller/state, model, and widget boundaries.
- Make photo browsing fast through cursor pagination, page caching, timeline buckets, lazy rendering, image caching, and preview prefetch only near detail-view focus.
- Prefer local files over backend binaries when a confident local match exists.
- Support selected-folder backup with duplicate avoidance and retryable upload state.
- Expose all backend-supported management surfaces: albums/tags, search, people/faces, jobs, notifications, diagnostics, trash, and date/time edits.
- Document backend gaps and mobile limitations in `mobile/README.md`.

**Non-Goals:**
- Add or change backend endpoints as part of this change.
- Implement cloud push notifications or remote background execution infrastructure beyond clean local polling/local notification hooks if cheap.
- Guarantee identical iOS folder-picker semantics if plugin/platform APIs cannot expose Android-style folders.
- Implement ML or image processing on-device beyond media metadata/file matching needed for backup/local resolution.

## Decisions

### Feature-first Flutter structure
Use feature folders under `lib/src/features/<feature>/` with `data/`, `domain/`, `presentation/`, and lightweight `application/` controllers where useful. Shared API, routing, theming, persistence, widgets, and utilities live under `lib/src/shared/`.

Alternative considered: layer-first `api/`, `models/`, `pages/` top-level structure. Rejected because this app spans many backend domains and feature ownership is easier to maintain with feature-first boundaries.

### Manual typed DTOs generated from OpenAPI shape, not dynamic maps in UI
Define explicit Dart DTOs for backend schemas used by mobile, with `fromJson`/`toJson` helpers. Keep unknown JSON blobs as `Map<String, dynamic>` only for backend fields that are explicitly arbitrary (`parameters`, `result`, `details`, diagnostics summaries, EXIF).

Alternative considered: fully generated OpenAPI client. Rejected for initial implementation because current project has no generation pipeline and manual DTOs keep contracts readable; `backend/openapi-schema.json` remains source of truth and README documents regeneration as future work.

### Central HTTP client with auth/session handling
Use one API client that stores base URL, attaches `Authorization: Bearer`, maintains refresh-cookie state, retries once on `401` via `/auth/refresh`, and redirects to login when refresh fails. Store access token/session metadata in secure storage. Persist base URL and non-secret settings locally.

Alternative considered: per-feature clients each handle tokens. Rejected due to duplicate logic and higher risk of token leaks.

### Riverpod-based state plus repository caching
Use Riverpod for async state/controllers and repositories with in-memory page caches per filter key. Use local persistence for auth/settings/backup/local-index state. Do not refetch already loaded cursor pages when returning to a screen unless user refreshes or relevant mutation invalidates the key.

Alternative considered: BLoC. Rejected because Riverpod is lighter for async repositories and feature-scoped controllers while still testable.

### Timeline grid uses backend buckets plus paged assets
Fetch `/timeline/months` for fast scroller labels/jump targets and fetch `/assets` pages for visible grid data. For month jumps, request `GET /assets?month=YYYY-MM-01` rather than deep-offset paging. Group rendered assets by `timeline_day`/month derived from item fields.

Alternative considered: preload every month page. Rejected because large libraries would waste API calls and memory.

### Detail viewer uses local-first resolver and preview ensure window
When opening/swiping detail, resolve current asset against local index using strong matches first: backend `file_hash`, then combinations of file size, filename/master_path basename, captured/timeline timestamp, MIME/media kind, and local path hints. If confident local file exists, display it. Otherwise call `/assets/previews/ensure` for current ± small window and use returned/static `preview_url` when ready. Grid always uses `small_thumbnail_url` only.

Alternative considered: always fetch backend previews. Rejected because many assets may already exist on-device and unnecessary server traffic hurts UX.

### Backup state is local and idempotent
Selected device folders/albums are disabled by default. Scans enumerate local media via Flutter media/folder plugins, build/update a local index, compare against known backend asset IDs/hashes/size-name-time signatures, and upload only unknown files via multipart `/assets/upload`. Each local asset tracks upload status, matched backend ID, last attempt, error, and retry count.

Alternative considered: backend path ingest for device files. Rejected because `/assets/ingest` ingests server filesystem paths, not phone paths.

### Search tab is secondary navigation hub
Main bottom tabs are Photos, Albums, Search, Settings. Search contains keyword search, filters, People, Trash, Device folders, Jobs, Notifications, and Diagnostics entry cards. This matches the requested uncluttered primary navigation while exposing all backend features.

### Static media URLs use authenticated-capable image client where possible
Backend media routes are static and not represented as protected API routes. Use backend-provided URLs for thumbnails/previews and pass auth headers where the image loader supports it. If static routes do not require auth in backend, images still load; if auth is added later, centralized URL/header handling limits changes.

## Risks / Trade-offs

- Backend refresh relies on HttpOnly cookie semantics → mobile client must persist and resend refresh cookie from login/refresh responses; test against real backend.
- Static media routes currently bypass API auth → self-hosted deployments should rely on network boundary/reverse proxy until backend secures media endpoints.
- Local hash computation for many large videos can be expensive → compute hashes lazily/while charging where possible; start with metadata signatures and hash on demand for ambiguous matches/uploads.
- Flutter folder/media plugins differ by platform → Android gets richest support first; iOS may need Photos-library album abstraction instead of arbitrary folders.
- On-demand preview endpoint can return queued status before binary exists → viewer must show thumbnail/placeholder and poll/refetch asset or retry image after job completion.
- Very large timeline fast-scroller precision depends on backend month buckets, not exact per-pixel asset offsets → month jumps are accurate, intra-month position is approximate.
- Manual DTO drift is possible when backend schema changes → add README note and tests around JSON parsing for key schemas.

## Migration Plan

1. Add mobile dependencies, Android permissions, project structure, shared API/auth/config, DTOs, repositories, and tests.
2. Implement auth shell, app routing, theme, and common state widgets.
3. Implement library browsing/detail viewer and preview/local resolution.
4. Implement albums/tags/search/people/faces/trash/jobs/notifications/diagnostics/settings/backup screens incrementally.
5. Write `mobile/README.md` with implementation notes, backend gaps, validation, and follow-up items.
6. Validate with `flutter format`, `flutter analyze`, and `flutter test` from `mobile/`.

Rollback is limited to reverting `mobile/` changes because no backend migrations or API changes are introduced.

## Questions (Answered below)

- Which Flutter media/folder plugin set is acceptable for long-term Android/iOS support in this repo?
- Should static media routes become authenticated API routes later so mobile image URLs can be protected consistently?
- Should backend expose asset hash in grid responses to improve local-first matching without detail fetches?
- Should backend expose mobile-friendly backup manifests or dedupe-by-hash preflight endpoints to avoid upload attempts for known files?

### Decisions

#### Flutter media/folder plugin
Use `photo_manager` as the primary cross-platform media library abstraction. Treat selectable “folders” as device media albums/buckets, not raw filesystem directories. Use an OS-native background transfer plugin such as `background_downloader` for resilient uploads if needed. Android-specific MediaStore plugins may be used only as narrow platform helpers, not as the main abstraction.

#### Media route protection
Keep existing static media routes for the initial mobile implementation if the deployment remains LAN/Tailscale-only, but centralise media URL generation in the client. Plan a later backend change to serve media through short-lived signed URLs. Prefer signed URLs long-term so Flutter/web image and video widgets can load media normally while keeping access protected.

#### Asset hash in grid responses
Expose asset hash and related matching metadata to mobile list/grid responses, preferably behind an explicit `include_hash=true`. This avoids N+1 detail fetches and enables reliable local-first asset matching.

#### Backup dedupe/preflight
Add a batched dedupe-by-hash preflight endpoint before building a full mobile backup manifest system. The endpoint should let the mobile app submit hashes/file sizes for many local assets and receive known/unknown asset status. Add mobile backup manifests later if per-device reconciliation becomes necessary.
