## Why

The backend now exposes enough photo-library, search, people, jobs, notifications, tags/albums, trash, preview, upload, and auth APIs to support a real mobile client. The `mobile/` Flutter project is currently a placeholder, so users cannot browse, view, manage, or back up photos from a phone.

## What Changes

- Build a production-oriented Flutter mobile app in `mobile/` using the committed OpenAPI schema as the API contract source of truth.
- Add secure login/logout/session refresh, centralized API config, typed DTOs, repositories, feature controllers, and reusable loading/error/empty UI states.
- Implement bottom-tab navigation for Photos, Albums, Search, and Settings.
- Implement paginated timeline browsing with month grouping, cached pages, lazy grids, timeline month data, fast scrolling, thumbnails, blurhash-style placeholders where available, and fullscreen asset detail viewing.
- Implement local-first media resolution and backup-folder support so device files can be matched to backend assets and uploaded without duplicates.
- Implement albums/tags browsing and editing, hierarchical paths, album/tag asset grids, and single/batch asset membership operations where supported.
- Implement search with debounced text queries plus person/tag/album filters, people entry points, device folders, and trash access from Search.
- Implement people/faces management, including people listing/detail/name/hide/merge, face assignment, confirmation, denial/exclusion, face processing, and matching actions where supported.
- Implement jobs, system integrity diagnostics, and notifications pages, including manual job launching and read/delete notification flows.
- Implement trash browsing, restore, permanent delete, empty trash, and destructive-action confirmations.
- Implement date/time editing and asset metadata/actions supported by the backend.
- Document backend gaps, mobile limitations, implementation notes, validation commands, and follow-up work in `mobile/README.md`.

## Capabilities

### New Capabilities
- `mobile-auth-and-api`: Mobile app connects to a configured self-hosted backend, authenticates, refreshes sessions, persists tokens securely, and handles API errors consistently.
- `mobile-library-browsing`: Mobile app browses large active libraries via cursor pagination, timeline buckets, lazy grids, cached pages, month grouping, and detail viewer preview flows.
- `mobile-local-media-and-backup`: Mobile app indexes selected device folders/albums, matches local files to backend assets, prefers local binaries, and uploads new selected media without duplicates.
- `mobile-taxonomy-management`: Mobile app browses and manages hierarchical tags and tag-backed albums, including descendant-aware filtering and asset membership operations.
- `mobile-search-people-faces`: Mobile app performs backend search, combines supported filters, lists/names people, and exposes supported face confirmation/assignment/exclusion flows.
- `mobile-operations-trash-settings`: Mobile app exposes jobs, system integrity diagnostics, notifications, trash, destructive actions, date/time edits, and settings screens.

### Modified Capabilities

None.

## Impact

- Affected code: `mobile/` Flutter app source, platform config, tests, dependencies, and `mobile/README.md`.
- API usage: existing `/api/v1` auth, assets, timeline, search, tags, albums, people, faces, jobs, notifications, system integrity, trash, and static media routes.
- Dependencies: Flutter HTTP/client libraries, secure token storage, local persistence, cached image loading, media/folder access, permissions, file picking/media indexing, and upload support.
- Systems: Android-first mobile media permissions and local file indexing; iOS support should use Flutter-compatible abstractions but may require platform-specific follow-up for folder semantics.
