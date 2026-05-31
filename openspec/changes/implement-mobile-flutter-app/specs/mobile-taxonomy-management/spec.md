## ADDED Requirements

### Requirement: Album browsing
The mobile app SHALL list tag-backed albums, render hierarchy where available, and open album asset grids using backend album endpoints.

#### Scenario: Albums tab opens
- **WHEN** the user opens Albums
- **THEN** the app fetches album nodes and displays album names, hierarchy/path context, and cover information when available

#### Scenario: Open album
- **WHEN** the user selects an album
- **THEN** the app loads that album's assets using the backend album assets endpoint with cursor pagination

### Requirement: Tag browsing and search
The mobile app SHALL browse hierarchical tags and allow users to use tags as asset filters.

#### Scenario: Tag hierarchy loads
- **WHEN** the user opens tag browsing
- **THEN** the app fetches tag nodes and displays parent/child relationships from tag path/parent metadata

#### Scenario: Filter by multiple tags
- **WHEN** the user selects multiple tag filters
- **THEN** the app sends all selected tag IDs to supported backend asset/search endpoints using AND semantics supplied by the backend

### Requirement: Create and edit tags/albums
The mobile app SHALL create, rename, move, describe, set cover, and delete tags/albums when supported by backend endpoints.

#### Scenario: Create child album
- **WHEN** the user creates an album with a parent
- **THEN** the app calls the album create endpoint with `parent_id` and refreshes album lists

#### Scenario: Delete branch requires confirmation
- **WHEN** deleting a tag/album branch fails because children exist
- **THEN** the app shows a confirmation path and retries with `delete_children=true` only after explicit user confirmation

### Requirement: Asset membership management
The mobile app SHALL add/remove assets to/from tags/albums using single-item or batch endpoints where supported.

#### Scenario: Add current asset to album
- **WHEN** the user adds one asset to an album from detail view
- **THEN** the app calls the asset tag add endpoint and updates local detail state

#### Scenario: Batch add selected assets
- **WHEN** the user adds multiple selected assets to a tag/album
- **THEN** the app uses the backend batch-add endpoint and refreshes affected grids/details
