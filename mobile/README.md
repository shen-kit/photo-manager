# Photo Manager Mobile

Flutter mobile client for the self-hosted Photo Manager backend.

## Implemented

- Dark, minimal Flutter app with bottom tabs:
  - Photos
  - Albums
  - Search
  - Settings
- Secure-ish mobile auth flow:
  - configurable backend URL
  - username/password login
  - access token storage via `flutter_secure_storage`
  - refresh-cookie capture/resend for `/api/v1/auth/refresh`
  - logout clears local session
- Central API client:
  - `/api/v1` route construction
  - bearer auth injection
  - JSON decode/error mapping
  - multipart upload support
  - media URL resolution
  - one retry after refresh on `401`
- Typed Dart models based on `backend/openapi-schema.json` for main app surfaces:
  - auth/user
  - asset grid/detail/page
  - timeline months
  - preview ensure
  - tags/albums
  - people/faces
  - jobs/manual jobs
  - notifications
  - trash
  - diagnostics
  - local backup/index state
- Photos timeline:
  - cursor-paginated active asset feed (`GET /api/v1/assets/`)
  - in-memory page cache per filter
  - month grouping
  - lazy thumbnail grid using `small_thumbnail_url`
  - month fast-scroller backed by `/api/v1/timeline/months`
  - no full preview loads in grid cells
- Asset detail viewer:
  - fullscreen dark viewer
  - swipe between loaded assets
  - bottom thumbnail strip
  - large preview/video loading only in detail
  - neighbour preview ensure via `/api/v1/assets/previews/ensure`
  - local-first file resolution before backend preview fetch
  - edit captured date/time
  - favorite toggle
  - soft delete to trash
  - tag/album membership and face actions from detail management page
- Local media and backup:
  - Android-first/cross-platform `photo_manager` media permission + album/folder discovery
  - no backup folders selected by default
  - selected source persistence
  - local media index persisted in shared preferences
  - hash/metadata-based local asset resolver
  - duplicate-safe upload state tracking
  - upload selected unknown files via `/api/v1/assets/upload`
- Albums/tags:
  - album list/detail grid
  - tag browser
  - create tag/album
  - add/remove current asset to/from tag/album
  - batch repository methods for backend batch endpoints
- Search:
  - debounced keyword search via `/api/v1/search/`
  - tag filter support
  - recent searches
  - Search hub links for People, Trash, Device folders, Jobs, Notifications
- People/faces:
  - people listing with thumbnails/counts
  - person detail asset grid using `person_ids` filter
  - rename person
  - face list per asset
  - confirm face
  - exclude/deny face
  - assign face to person
  - process/match faces actions
- Jobs/diagnostics/notifications:
  - jobs list/progress
  - available manual jobs and run buttons disabled while active
  - diagnostics list and run action
  - notifications list, mark read/all read, delete/all delete
- Trash:
  - trash-only page via `/api/v1/trash/assets/`
  - restore
  - permanent delete confirmation
  - empty trash confirmation
  - active grids only use active asset endpoints
- Tests:
  - DTO parsing
  - tag/search state
  - backup source selection persistence
  - local media index upload-state persistence
  - local-vs-remote resolver matching/ambiguity

## Architecture

```text
lib/src/
  app.dart
  shared/
    api/              # ApiClient, errors, auth retry
    config/           # AppSettingsStore
    models/           # typed DTOs/domain models
    providers.dart    # shared Riverpod providers
    storage/          # secure session store
    theme/            # dark Material theme
    utils/            # redacting logger
    widgets/          # image, async state, confirmation dialogs
  features/
    auth/
    assets/
    albums/
    tags/
    search/
    people/
    faces/
    jobs/
    notifications/
    trash/
    backup/
    settings/
```

State management uses Riverpod. Repositories own API calls and lightweight caching. UI widgets request only the data needed by the current screen.

## Local-first media strategy

The app indexes selected device media sources from `photo_manager` albums/buckets. Matching prefers:

1. SHA-256 equals backend `file_hash`.
2. Strong metadata combinations:
   - media kind/MIME compatible
   - filename or backend `master_path` basename match
   - file size match
   - captured/created/modified timestamp within a small tolerance

Ambiguous weak matches are rejected. Detail viewer uses local file only when resolver returns exactly one confident available match; otherwise it uses backend preview ensure + preview URL.

## Backend/API gaps and assumptions

- Grid responses do not include `file_hash`, `master_path`, or `file_size_bytes`; reliable local matching often requires detail fetch. Better backend: optional `include_hash=true` on grid/search endpoints.
- No mobile backup preflight endpoint exists. Current app avoids duplicates through local match state and backend upload dedupe, but a batched hash preflight endpoint would reduce uploads/API churn.
- `/api/v1/assets/ingest` is server-path ingest, not useful for phone files; mobile uses multipart upload.
- Static media URLs under `/media/processed` and `/media/originals` are not API-authenticated in current backend. App passes auth headers where possible, but backend/reverse proxy must protect media if deployment is not private network only. Long-term: signed URLs or authenticated media endpoints.
- Preview ensure may return queued/pending before binary exists. Viewer keeps placeholder and can retry after jobs progress.
- Device “folders” are implemented as platform media albums/buckets via `photo_manager`, not arbitrary filesystem directories. This is portable but may differ from Android file-manager folder semantics.
- Local push notifications were not added. Reason: backend has in-app notifications only; robust push/local notifications would require polling/background scheduling policy and platform-specific notification UX. Current app documents/uses in-app notification polling on page open.
- iOS backup behavior needs device testing. Android is primary target.

## Validation commands run

```bash
cd mobile && flutter pub get
cd mobile && dart format lib test
cd mobile && flutter analyze
cd mobile && flutter test
openspec validate implement-mobile-flutter-app
```

Results:

- `flutter pub get`: passed
- `dart format lib test`: passed
- `flutter analyze`: passed, no issues
- `flutter test`: passed, 7 tests
- `openspec validate implement-mobile-flutter-app`: passed

## Manual verification checklist

Requires running backend and device/emulator media library:

- Login/logout
- Load photo grid
- Infinite scroll
- Month fast scroller/jump
- Open detail viewer
- Swipe between assets
- Bottom thumbnail strip
- Backend preview ensure and queued placeholder behavior
- Local file preferred over backend preview when local index confidently matches
- Select backup folders/albums
- Scan selected folders/albums
- Upload new media
- Search by keyword
- Filter search by tags
- View albums and album assets
- View/name people
- Confirm/exclude/assign faces
- Process/match faces
- View jobs and run manual jobs
- View diagnostics and run checks
- View notifications and mark/delete
- Trash restore/permanent delete/empty trash
- Edit captured date/time

## Remaining TODOs

- Add a backend mobile backup preflight endpoint: batch hash/size lookup.
- Add optional hash/path/size fields to lightweight grid/search responses for local-first matching without N+1 detail calls.
- Add signed/authenticated media URL backend support.
- Expand dynamic manual job parameter forms beyond default params.
- Add robust background upload scheduling for Android/iOS.
- Add local notification integration if background polling requirements are clarified.
- Add widget tests for full navigation/detail viewer once test media fixtures are available.
