## ADDED Requirements

### Requirement: Jobs and diagnostics
The mobile app SHALL list jobs, display job details/progress, list available manual jobs, run jobs when allowed, and expose system integrity diagnostics/repairs.

#### Scenario: Jobs page opens
- **WHEN** the user opens Jobs
- **THEN** the app fetches jobs and displays status, progress, timestamps, and error/result details when available

#### Scenario: Run manual job
- **WHEN** the user starts an available manual job that is not already active
- **THEN** the app calls the manual job run endpoint and disables duplicate run action while active status is exposed

#### Scenario: Run diagnostic repair
- **WHEN** the user opens a repairable diagnostic run and confirms repair
- **THEN** the app calls the repair endpoint and updates diagnostic/job state

### Requirement: Notifications
The mobile app SHALL display backend notifications in-app and support mark-read and delete flows.

#### Scenario: Notifications page opens
- **WHEN** the user opens Notifications
- **THEN** the app fetches notifications and shows level, category, title, message, timestamps, and read state

#### Scenario: Mark all read
- **WHEN** the user marks all notifications read
- **THEN** the app calls the backend read-all endpoint and updates local notification state

### Requirement: Trash management
The mobile app SHALL list trashed assets separately from normal grids and support restore, permanent delete, bulk operations, and empty trash where backend supports them.

#### Scenario: Trash page opens
- **WHEN** the user opens Trash from Search
- **THEN** the app fetches trashed assets from trash endpoints rather than active asset endpoints

#### Scenario: Restore asset
- **WHEN** the user restores a trashed asset
- **THEN** the app calls the restore endpoint and removes the asset from trash view after success

#### Scenario: Permanent delete confirmation
- **WHEN** the user requests permanent delete or empty trash
- **THEN** the app requires explicit confirmation before calling destructive backend endpoints

### Requirement: Asset metadata and actions
The mobile app SHALL expose supported asset actions from detail views, including captured date/time edit, favorite/description edit, soft delete, tag/album membership, people/faces, and trash-only restore/permanent delete.

#### Scenario: Edit captured date/time
- **WHEN** the user saves a new captured date/time for an active asset
- **THEN** the app patches `captured_at` using backend field semantics and updates local grids/details after success

#### Scenario: Soft delete active asset
- **WHEN** the user deletes an active asset
- **THEN** the app calls the active asset delete endpoint and removes the asset from active cached grids

### Requirement: Settings and app state
The mobile app SHALL provide Settings for backend URL/account, logout, backup folder selection, backup/upload status, and local cache/index maintenance.

#### Scenario: Settings opens
- **WHEN** the user opens Settings
- **THEN** the app displays account/backend info, backup controls, and maintenance actions without exposing tokens

#### Scenario: Clear local cache
- **WHEN** the user clears local media/API cache
- **THEN** the app removes non-secret cached pages/index entries as requested while preserving selected settings unless explicitly reset
