## ADDED Requirements

### Requirement: Device media permission handling
The mobile app SHALL request and respect platform media permissions before scanning device media or backup folders.

#### Scenario: Permission granted
- **WHEN** the user grants required media permissions
- **THEN** the app scans available media folders/albums and shows selectable sources

#### Scenario: Permission denied
- **WHEN** the user denies required media permissions
- **THEN** the app shows a clear disabled state and instructions to enable access

### Requirement: Backup folder selection
The mobile app SHALL detect folders or platform media collections containing photos/videos and SHALL let users select/deselect them for automatic backup, with no folders selected by default.

#### Scenario: First settings visit
- **WHEN** the user opens backup settings for the first time
- **THEN** no device folders are selected for backup

#### Scenario: Select folder
- **WHEN** the user selects a detected folder
- **THEN** the app persists that selection and includes it in future backup scans

### Requirement: Local media index
The mobile app SHALL maintain a local index of discovered media from selected sources with stable metadata used for backend asset matching.

#### Scenario: Scan selected sources
- **WHEN** backup scan runs
- **THEN** the app records local path/URI, filename, size, media kind, timestamps, MIME where available, optional hash, and scan status

#### Scenario: Local file removed
- **WHEN** an indexed local file is no longer available
- **THEN** the app marks it unavailable and stops using it for local-first viewing

### Requirement: Local-first asset resolution
The mobile app SHALL prefer a local file for viewing when it can confidently match a backend asset using hash or strong metadata combinations.

#### Scenario: Hash match
- **WHEN** a local indexed file hash equals the backend asset `file_hash`
- **THEN** the viewer uses the local file instead of downloading backend media

#### Scenario: Ambiguous match
- **WHEN** multiple local files match weak metadata for one backend asset
- **THEN** the app treats the match as not confident and uses the backend preview flow

### Requirement: Duplicate-safe backup uploads
The mobile app SHALL avoid re-uploading files already matched to backend assets and SHALL track upload state locally.

#### Scenario: Already matched asset
- **WHEN** a selected local file is matched to a backend asset
- **THEN** the app does not upload that file again

#### Scenario: New file upload
- **WHEN** a selected local file has no confident backend match
- **THEN** the app uploads it with the backend multipart upload endpoint and stores the returned backend asset ID/hash

#### Scenario: Upload failure retry
- **WHEN** an upload fails due to network or server error
- **THEN** the app records failure details, exposes retry, and avoids concurrent duplicate upload attempts for the same file
