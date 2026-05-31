## ADDED Requirements

### Requirement: Debounced semantic search
The mobile app SHALL search backend assets using the search endpoint with debounced keyword input and supported filters.

#### Scenario: User types query
- **WHEN** the user types in the search field
- **THEN** the app waits for debounce before issuing a search request

#### Scenario: Query plus filters
- **WHEN** the user combines keyword, people, and tag/album filters
- **THEN** the app sends supported query parameters to the backend search endpoint

#### Scenario: Empty search state
- **WHEN** no query or filters are active
- **THEN** the app shows useful entry points such as People, Trash, Device folders, Jobs, Notifications, and recent searches if available

### Requirement: People list and detail
The mobile app SHALL list people, support name/hide updates, and show person-filtered asset grids using backend person and asset filter endpoints.

#### Scenario: People page opens
- **WHEN** the user opens People from Search
- **THEN** the app fetches visible people and displays names, counts, and thumbnails when available

#### Scenario: Rename person
- **WHEN** the user edits a person's name
- **THEN** the app patches that person and updates local person/search state

#### Scenario: Open person detail
- **WHEN** the user selects a person
- **THEN** the app loads active assets filtered by that person's ID

### Requirement: Face correction flows
The mobile app SHALL expose backend-supported face confirmation, denial/exclusion, person assignment, asset face processing, and matching flows.

#### Scenario: Confirm face
- **WHEN** the user confirms a face belongs to its assigned person
- **THEN** the app patches the face with `is_confirmed=true`

#### Scenario: Deny face
- **WHEN** the user marks a face/person assignment incorrect
- **THEN** the app patches the face to clear or exclude the assignment according to user action

#### Scenario: Assign face to person
- **WHEN** the user assigns a face to a selected person
- **THEN** the app patches the face `person_id` and refreshes affected asset/person data

### Requirement: People merge and thumbnails
The mobile app SHALL support people merge and person thumbnail updates where backend endpoints support them.

#### Scenario: Merge people
- **WHEN** the user confirms merging one person into another
- **THEN** the app calls the merge endpoint and removes/refreshes affected people from local state

#### Scenario: Set person thumbnail
- **WHEN** the user selects an asset as a person's thumbnail
- **THEN** the app calls the thumbnail update endpoint and refreshes the person thumbnail URL
