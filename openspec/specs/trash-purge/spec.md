## ADDED Requirements

### Requirement: Permanently delete one trashed asset
The system SHALL allow an authenticated client to permanently delete a single asset only when that asset is already in trash. Permanent deletion MUST remove the original media file, remove generated processed asset files, and delete the asset row so dependent database records are cleaned up by existing database constraints.

#### Scenario: Single trashed asset is permanently deleted
- **WHEN** client requests permanent deletion for an asset whose `deleted_at` is set
- **THEN** system deletes the asset's original file from the originals media root
- **THEN** system deletes the asset's processed files from the processed media root
- **THEN** system deletes the asset database row

#### Scenario: Active asset cannot be permanently deleted
- **WHEN** client requests permanent deletion for an asset whose `deleted_at` is null
- **THEN** system MUST reject the request without deleting any files or database rows

### Requirement: Permanently delete many trashed assets with partial-failure reporting
The system SHALL support bulk permanent deletion for a client-provided list of asset IDs. The system MUST deduplicate repeated IDs before work begins and MUST attempt each eligible trashed asset independently so one failure does not block unrelated purges.

#### Scenario: Bulk purge deletes eligible assets and reports failures
- **WHEN** client submits a bulk permanent-delete request containing both valid trashed asset IDs and invalid or non-trashed asset IDs
- **THEN** system permanently deletes each eligible trashed asset
- **THEN** system returns aggregate deleted and failed counts
- **THEN** system returns failure details for each asset that could not be purged

#### Scenario: Duplicate asset IDs are ignored
- **WHEN** client submits a bulk permanent-delete request containing the same asset ID more than once
- **THEN** system processes that asset at most once

### Requirement: Empty trash without affecting active assets
The system SHALL support permanently deleting every asset currently in trash. This operation MUST target only assets whose `deleted_at` is set and MUST leave active assets unchanged.

#### Scenario: Empty trash purges only trashed assets
- **WHEN** client requests to empty trash
- **THEN** system permanently deletes all assets whose `deleted_at` is set
- **THEN** system does not delete any asset whose `deleted_at` is null

#### Scenario: Empty trash succeeds when trash is already empty
- **WHEN** client requests to empty trash and no assets are currently trashed
- **THEN** system returns success with zero deleted assets

### Requirement: Permanent deletion MUST stay within configured media roots
The system MUST resolve purge file targets using constrained media-root path logic. Invalid or escaping paths MUST block permanent deletion for that asset, and the asset database row MUST remain so the failure can be retried or repaired safely.

#### Scenario: Invalid original path blocks purge
- **WHEN** a trashed asset has a stored original path that resolves outside the originals media root or cannot be validated
- **THEN** system MUST not delete the asset database row
- **THEN** system MUST report the purge as failed

#### Scenario: Missing files do not prevent final cleanup
- **WHEN** a trashed asset references an original file or processed directory that no longer exists but resolves within the expected media root
- **THEN** system treats the missing files as already absent
- **THEN** system still deletes the asset database row
