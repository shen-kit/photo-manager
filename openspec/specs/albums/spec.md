## ADDED Requirements

### Requirement: Albums SHALL be manageable through authenticated API endpoints
The system SHALL expose album workflows through tags where `is_album = true`. Album records SHALL live in the existing `tags` table and SHALL use the same hierarchy, slug, path, cover, and timestamp model as normal tags.

#### Scenario: Create album
- **WHEN** client creates album named `Summer 2024`
- **THEN** system creates tag row with `is_album = true`
- **AND** system stores ltree-safe slug and path for that album
- **AND** response returns tag id, name, slug, path, and `is_album = true`

#### Scenario: Rename album
- **WHEN** client renames album `Summer 2024` to `Summer 2024 Favorites`
- **THEN** system updates album name
- **AND** system updates slug and path leaf consistently
- **AND** descendant paths are updated in same transaction

#### Scenario: Move album subtree
- **WHEN** client moves album `summer_2024` under album `travel`
- **THEN** system updates album path using shared tag hierarchy rules
- **AND** descendant album paths are updated in same transaction

### Requirement: Album membership SHALL use explicit tag assignments only
Album membership SHALL be represented by explicit rows in `asset_tags` exactly like normal tag assignment. The system SHALL NOT create extra album membership rows for ancestors when an asset is tagged with a descendant album.

#### Scenario: Explicit child album membership does not materialize parent album
- **WHEN** asset is tagged only with album `holidays.china_2026`
- **THEN** system stores only explicit join to `holidays.china_2026`
- **AND** system does not create explicit join to album `holidays`

#### Scenario: Viewing parent album includes descendant explicit memberships
- **WHEN** asset is tagged only with album `holidays.china_2026`
- **AND** client views album `holidays`
- **THEN** asset appears because selected album matches descendant explicit membership

#### Scenario: Removing child album membership preserves explicit parent album membership
- **WHEN** asset is explicitly tagged with albums `holidays` and `holidays.china_2026`
- **AND** client removes `holidays.china_2026`
- **THEN** explicit album `holidays` remains on asset

#### Scenario: Removing parent album membership preserves explicit child album membership
- **WHEN** asset is explicitly tagged with albums `holidays` and `holidays.china_2026`
- **AND** client removes `holidays`
- **THEN** explicit album `holidays.china_2026` remains on asset

### Requirement: Album retrieval SHALL use descendant-aware filtering with AND semantics
Album filtering and album detail asset listing SHALL use same descendant-aware matching rules as normal tags. Multiple selected albums SHALL use AND semantics by default.

#### Scenario: List albums
- **WHEN** client requests album list
- **THEN** response includes only tags where `is_album = true`
- **AND** each item includes id, name, slug, path, parent path, `cover_asset_id`, and timestamps

#### Scenario: Get album detail
- **WHEN** client requests specific album
- **THEN** response includes album metadata
- **AND** asset results include assets tagged directly with that album or any descendant album
- **AND** asset items reuse existing browse grid and asset detail shapes used elsewhere in backend

#### Scenario: Multiple album filters use AND semantics
- **WHEN** asset has explicit descendant-album matches under both `holidays` and `family`
- **AND** client filters by albums `holidays` and `family`
- **THEN** asset is included
- **AND** asset lacking either branch is excluded

### Requirement: Album covers SHALL use descendant-aware validation
Albums SHALL support `cover_asset_id`, and cover validation SHALL succeed only when cover asset belongs to album directly or through descendant album membership.

#### Scenario: Set valid album cover from descendant membership
- **WHEN** client sets cover for album `holidays`
- **AND** asset is explicitly tagged with descendant album `holidays.china_2026`
- **THEN** system accepts `cover_asset_id`

#### Scenario: Reject invalid album cover
- **WHEN** client sets cover for album `holidays`
- **AND** asset has no explicit album membership under `holidays`
- **THEN** system rejects request with validation error

### Requirement: Album deletion SHALL follow tag subtree deletion rules
Deleting albums SHALL delete tag rows and matching `asset_tags` rows according to shared tag delete semantics without modifying asset records beyond removed joins.

#### Scenario: Delete leaf album
- **WHEN** client deletes album with no descendants
- **THEN** system removes album row and related `asset_tags` joins

#### Scenario: Delete album branch requires confirmation by default
- **WHEN** client deletes album that has descendants without specifying `delete_children`
- **THEN** system treats `delete_children` as `false`
- **AND** system returns conflict-style HTTP response suitable for frontend confirmation dialog

#### Scenario: Confirmed delete of album branch
- **WHEN** client deletes album that has descendants using `delete_children=true`
- **THEN** system deletes album subtree and related `asset_tags` joins
