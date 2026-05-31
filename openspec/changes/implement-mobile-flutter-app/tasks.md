## 1. Project Setup and Shared Foundation

- [x] 1.1 Add Flutter dependencies for HTTP, Riverpod, secure storage, local persistence, routing, cached images, media access, file picking, permissions, upload, video playback, and testing.
- [x] 1.2 Configure Android media/network permissions and platform settings without hard-coding Android-only logic into shared code.
- [x] 1.3 Create feature-first `lib/src/` structure for auth, assets, albums, tags, search, people, faces, jobs, notifications, trash, backup, settings, and shared modules.
- [x] 1.4 Implement dark minimal app theme, bottom navigation shell, app router, and common loading/empty/error/retry widgets.
- [x] 1.5 Implement shared logging helpers that never log tokens, passwords, cookies, or full local media paths unless debug-safe.

## 2. API, Models, Auth, and Persistence

- [x] 2.1 Define typed Dart DTOs/models for backend schemas used by mobile from `backend/openapi-schema.json`.
- [x] 2.2 Implement centralized API client with base URL config, JSON handling, multipart upload, query building, media URL resolution, timeout/error mapping, and auth header injection.
- [x] 2.3 Implement refresh-cookie capture/storage/resend and one-time refresh retry on `401`.
- [x] 2.4 Implement secure session storage for access token/session metadata and local settings storage for backend URL and non-secret preferences.
- [x] 2.5 Implement auth repository/controller for login, register if exposed in UI, me/session restore, refresh, logout, and expired-session redirect.
- [x] 2.6 Add unit tests for token/session handling, refresh retry, error mapping, and key DTO JSON parsing.

## 3. Asset Browsing and Detail Viewer

- [x] 3.1 Implement asset, timeline, preview, and metadata repositories with cache keys per filter and no redundant loaded-page refetch on navigation return.
- [x] 3.2 Implement Photos tab timeline grid with cursor pagination, month/day grouping, lazy thumbnails, placeholder rendering, and active-only filters.
- [x] 3.3 Implement month fast scroller using `/timeline/months` and month-filtered asset fetches for jumps.
- [x] 3.4 Implement fullscreen asset detail viewer with swipe navigation, dark UI, video playback support, bottom thumbnail strip, and metadata/action sheet.
- [x] 3.5 Implement preview ensure/prefetch for current ± neighbour window and retry/placeholder handling for queued previews.
- [x] 3.6 Implement date/time, favorite, description, soft-delete, and tag/album action integration in detail view.
- [x] 3.7 Add widget/unit tests for pagination cache, filter cache invalidation, month grouping, and preview prefetch window logic.

## 4. Local Media Index and Backup

- [x] 4.1 Implement platform media permission service and selected source/folder persistence with no default selected folders.
- [x] 4.2 Implement device media source discovery and Settings UI for selecting/deselecting backup folders or platform media collections.
- [x] 4.3 Implement local media index persistence with path/URI, filename, size, timestamps, MIME/media kind, optional hash, availability, match state, and upload state.
- [x] 4.4 Implement local-first asset resolver with confidence scoring using hash first and strong metadata combinations otherwise.
- [x] 4.5 Integrate local resolver into detail viewer so confident local files replace backend preview downloads.
- [x] 4.6 Implement selected-source scan, duplicate avoidance, multipart `/assets/upload`, upload progress/status, retry/failure handling, and no concurrent duplicate uploads.
- [x] 4.7 Add tests for local-vs-remote resolution, backup folder selection state, and duplicate-safe upload state transitions.

## 5. Albums, Tags, Search, People, and Faces

- [x] 5.1 Implement albums repository/controllers and Albums tab list/detail grids with hierarchy, covers, cursor paging, create/edit/delete, and delete-children confirmation.
- [x] 5.2 Implement tags repository/controllers and tag browsing/search/filtering with hierarchy/path display and create/edit/delete support.
- [x] 5.3 Implement single and batch add/remove asset-to-tag/album membership flows with local cache invalidation.
- [x] 5.4 Implement Search tab with debounced keyword search, person/tag/album filters, recent/empty state, and result pagination.
- [x] 5.5 Implement People pages for list/detail, thumbnails, rename/hide, person-filtered grids, merge, and thumbnail update.
- [x] 5.6 Implement face list/action UI for asset faces, confirm, deny/exclude, assign person, process faces, and match faces where backend supports it.
- [x] 5.7 Add tests for tag/album path handling, search debounce/filter state, people updates, and face patch payloads.

## 6. Operations, Trash, Notifications, and Settings

- [x] 6.1 Implement Trash page accessible from Search with page-based listing, detail viewing, restore, bulk restore, permanent delete, bulk delete, and empty trash confirmations.
- [x] 6.2 Implement Jobs page with job list/detail, progress display, available manual jobs, dynamic parameter form where practical, and active-job run-button disabling.
- [x] 6.3 Implement System Integrity pages with diagnostics list, latest/runs/items views, run diagnostic, and repair confirmation flows.
- [x] 6.4 Implement Notifications page with list/filter, unread state, mark one/all read, delete one/all, and documented local-notification decision.
- [x] 6.5 Finish Settings page with backend/account info, logout, backup controls/status, cache/index maintenance, and implementation notes entry.
- [x] 6.6 Ensure normal grids exclude trash by only using active asset endpoints, and trash screens only use trash endpoints.

## 7. Documentation and Validation

- [x] 7.1 Write `mobile/README.md` with architecture, implemented features, API/backend gaps, local media strategy, validation commands, manual verification checklist, and remaining TODOs.
- [x] 7.2 Run `dart format`/`flutter format` for `mobile/`.
- [x] 7.3 Run `flutter analyze` from `mobile/` and fix actionable findings.
- [x] 7.4 Run `flutter test` from `mobile/` and fix failing tests.
- [x] 7.5 Run `openspec validate implement-mobile-flutter-app` and fix proposal/spec/task validation errors.
- [ ] 7.6 Manually verify login/logout, grid load, month jump, detail swipe, thumbnail strip, local-first display, backup folder select/upload, search, people/faces, albums/tags, jobs/diagnostics/notifications, trash, and date/time edit against a running backend.
