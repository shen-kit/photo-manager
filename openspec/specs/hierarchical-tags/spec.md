## ADDED Requirements

### Requirement: Hierarchical tags SHALL be manageable through authenticated API endpoints
The system SHALL provide authenticated endpoints to create, list, rename, move, and delete non-album tags organized as a hierarchy. Each tag SHALL store a user-facing `name`, an ltree-safe `slug`, a unique hierarchical `path`, and explicit `is_album = false`.

#### Scenario: Create root tag
- **WHEN** client creates tag with name `Holidays` and no parent
- **THEN** system creates tag with a generated slug such as `holidays`
- **AND** system stores path `holidays`
- **AND** response includes tag id, name, slug, path, and `is_album = false`

#### Scenario: Create child tag
- **WHEN** client creates tag with name `China 2026` under parent path `holidays`
- **THEN** system stores slug `china_2026`
- **AND** system stores path `holidays.china_2026`
- **AND** response keeps display name `China 2026`

#### Scenario: Reject sibling slug collision
- **WHEN** client creates tag named `China-2026` under parent `holidays` after `China 2026` already exists there
- **THEN** system rejects request because both names normalize to same sibling slug

#### Scenario: Rename tag
- **WHEN** client renames tag `holidays.china_2026` to `China Trip 2026`
- **THEN** system updates tag name
- **AND** system updates slug and path leaf consistently
- **AND** system updates descendant paths in same transaction

#### Scenario: Move tag
- **WHEN** client moves tag `holidays.china_2026` under parent path `travel`
- **THEN** system updates tag path to `travel.china_2026`
- **AND** descendant paths are updated to preserve subtree structure

#### Scenario: Move subtree
- **WHEN** client moves tag `holidays` under `places`
- **THEN** descendants such as `holidays.china_2026` become `places.holidays.china_2026`

#### Scenario: Reject move under descendant
- **WHEN** client attempts to move tag `holidays` under `holidays.china_2026`
- **THEN** system rejects request with validation error

### Requirement: Asset tag assignments SHALL remain explicit-only
The system SHALL store only explicitly-added tags in `asset_tags`. It SHALL NOT automatically insert parent tags when a child tag is assigned.

#### Scenario: Add child tag without parent materialization
- **WHEN** client adds tag `holidays.china_2026` to an asset
- **THEN** system stores only join to `holidays.china_2026`
- **AND** system does not create additional join to `holidays`

#### Scenario: Remove child explicit tag preserves parent explicit tag
- **WHEN** asset is explicitly tagged with both `holidays` and `holidays.china_2026`
- **AND** client removes `holidays.china_2026`
- **THEN** explicit tag `holidays` remains on asset

#### Scenario: Remove parent explicit tag preserves child explicit tag
- **WHEN** client removes `holidays`
- **THEN** explicit tag `holidays.china_2026` remains on asset

### Requirement: Asset tag APIs SHALL use single-add, single-remove, and batch mutation endpoints
The system SHALL support single-tag add/remove for one asset and batch add/remove for one or more tags across multiple assets. Single-item endpoints SHALL be primary; replace-all mutation SHALL NOT be required for core workflows.

#### Scenario: Add single tag to single asset
- **WHEN** client sends `POST /assets/{asset_id}/tags/{tag_id}`
- **THEN** system creates explicit join if missing
- **AND** repeated identical request succeeds idempotently

#### Scenario: Remove single tag from single asset
- **WHEN** client sends `DELETE /assets/{asset_id}/tags/{tag_id}`
- **THEN** system removes explicit join if present
- **AND** repeated identical request succeeds idempotently

#### Scenario: Batch add tags to multiple assets
- **WHEN** client submits batch add request with asset ids `[A, B]` and tag ids `[T1, T2]`
- **THEN** system validates all assets and tags before mutation
- **AND** system creates all missing explicit joins in one transaction

#### Scenario: Batch remove tags from multiple assets
- **WHEN** client submits batch remove request with asset ids `[A, B]` and tag ids `[T1, T2]`
- **THEN** system removes matching joins in one transaction
- **AND** missing joins are treated as no-op

#### Scenario: Reject unknown asset or tag in batch request
- **WHEN** batch request includes asset id or tag id that does not exist
- **THEN** system rejects request with validation error

### Requirement: Tag filtering SHALL match descendants and use AND semantics by default
Filtering assets by one or more tags SHALL match explicit tags assigned directly to those selected tags or any descendant of those selected tags. When multiple tags are selected, asset matching SHALL require every selected tag filter to match somewhere in the asset's explicit tag set.

#### Scenario: Parent filter matches descendant explicit tag
- **WHEN** asset is explicitly tagged only with `holidays.china_2026`
- **AND** client filters assets by `holidays`
- **THEN** asset is included because explicit tag is descendant of selected tag

#### Scenario: Multiple filters use AND semantics
- **WHEN** asset is explicitly tagged with descendants under both `holidays` and `family`
- **AND** client filters by tags `holidays` and `family`
- **THEN** asset is included
- **AND** asset lacking either branch is excluded

#### Scenario: Multiple parent filters match descendants independently
- **WHEN** asset is explicitly tagged with `holidays.china_2026` and `family.parents`
- **AND** client filters by `holidays` and `family`
- **THEN** asset is included

#### Scenario: Invalid filter tag id is rejected
- **WHEN** client requests filtering with a tag id that does not exist
- **THEN** system rejects request with validation error

### Requirement: Tag responses SHALL support hierarchy rendering and cover selection
The system SHALL expose enough metadata for clients to render tree views and manage tag covers.

#### Scenario: List tags
- **WHEN** client requests tag list
- **THEN** response includes each tag's id, name, slug, path, parent path or null, `is_album`, `cover_asset_id`, and timestamps

#### Scenario: Set valid cover from descendant membership
- **WHEN** client sets cover asset for tag `holidays`
- **AND** cover asset is explicitly tagged with `holidays.china_2026`
- **THEN** system accepts `cover_asset_id`

#### Scenario: Reject invalid cover
- **WHEN** client sets cover asset for tag `holidays`
- **AND** asset has no explicit tag under `holidays`
- **THEN** system rejects request with validation error

### Requirement: Tag deletion SHALL protect hierarchy integrity
The system SHALL prevent silent loss of nested taxonomy during delete operations.

#### Scenario: Delete leaf tag
- **WHEN** client deletes tag with no descendants
- **THEN** system removes tag and related asset-tag joins

#### Scenario: Delete branch requires confirmation by default
- **WHEN** client deletes tag with descendants without specifying `delete_children`
- **THEN** system treats `delete_children` as `false`
- **AND** system returns conflict-style HTTP response that indicates descendants exist
- **AND** response detail is suitable for frontend confirmation dialog

#### Scenario: Delete branch requires explicit flag
- **WHEN** client deletes tag with descendants using `delete_children=false`
- **THEN** system returns conflict-style HTTP response that indicates descendants exist

#### Scenario: Confirmed delete of branch
- **WHEN** client deletes tag with descendants using `delete_children=true`
- **THEN** system removes tag subtree and related asset-tag joins in one transaction
