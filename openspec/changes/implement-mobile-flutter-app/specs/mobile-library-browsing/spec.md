## ADDED Requirements

### Requirement: Paginated photo timeline
The mobile app SHALL browse active assets with backend cursor pagination and SHALL avoid refetching loaded pages unless filters change, user refreshes, or mutations invalidate cached data.

#### Scenario: Initial photo grid load
- **WHEN** the Photos tab opens after authentication
- **THEN** the app fetches the first active asset page and renders only lightweight grid data with small thumbnails

#### Scenario: Infinite scroll
- **WHEN** the user nears the end of loaded grid content and `has_more` is true
- **THEN** the app fetches the next page using `next_cursor`

#### Scenario: Return to grid
- **WHEN** the user returns from detail view to a previously loaded grid
- **THEN** the app reuses cached pages and scroll position without unnecessary API calls

### Requirement: Timeline buckets and fast scrolling
The mobile app SHALL use timeline month buckets to group assets and provide a month-based fast scroller for large libraries.

#### Scenario: Month buckets load
- **WHEN** Photos tab initializes or filters change
- **THEN** the app requests timeline months and displays month labels for fast navigation

#### Scenario: Jump to month
- **WHEN** the user selects or drags to a month in the fast scroller
- **THEN** the app loads/jumps to assets for that month using backend month filtering when needed

### Requirement: Lightweight grid rendering
The mobile app SHALL use lazy/virtualized grid rendering, dark minimal UI, thumbnail placeholders, and no full preview loads in grid cells.

#### Scenario: Grid cell rendering
- **WHEN** a grid cell becomes visible
- **THEN** it loads the asset small thumbnail and uses available placeholder metadata while loading

#### Scenario: Large library scroll
- **WHEN** the user scrolls through many assets
- **THEN** offscreen cells are disposed/recycled and scrolling remains smooth

### Requirement: Asset detail viewer
The mobile app SHALL open assets in a fullscreen dark detail viewer with swipe navigation, bottom thumbnail strip, metadata/actions, and preview loading only for focused/neighbouring assets.

#### Scenario: Open asset detail
- **WHEN** the user taps a grid item
- **THEN** the app opens fullscreen detail at that asset using the existing loaded list context

#### Scenario: Swipe between assets
- **WHEN** the user swipes to a neighbouring asset
- **THEN** the viewer updates focus, selected thumbnail, and action state without returning to the grid

#### Scenario: Preview prefetch
- **WHEN** the viewer focuses an asset
- **THEN** the app ensures/prefetches previews for a small neighbouring window only

### Requirement: Backend preview flow
The mobile app SHALL use backend preview URLs and `/assets/previews/ensure` when no local file is available.

#### Scenario: Preview already available
- **WHEN** preview ensure returns an item with ready/available preview URL
- **THEN** the viewer loads that URL for display/playback

#### Scenario: Preview queued
- **WHEN** preview ensure returns queued/pending status
- **THEN** the viewer keeps a thumbnail/placeholder visible and allows retry or automatic refresh after job progress
