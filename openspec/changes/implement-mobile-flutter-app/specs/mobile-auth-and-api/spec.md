## ADDED Requirements

### Requirement: Backend configuration
The mobile app SHALL let users configure the self-hosted backend base URL and SHALL centralize API route construction under `/api/v1`.

#### Scenario: Save backend URL
- **WHEN** a user enters and saves a valid backend URL
- **THEN** subsequent API and media requests use that backend URL

#### Scenario: Invalid backend URL
- **WHEN** a user enters an invalid or unreachable backend URL during login
- **THEN** the app shows an actionable error and does not store credentials

### Requirement: Login and logout
The mobile app SHALL support username/password login, persisted sessions, current-user loading, and logout using backend auth endpoints.

#### Scenario: Successful login
- **WHEN** login returns an auth response
- **THEN** the app securely stores the access token/session data and opens the authenticated shell

#### Scenario: Logout
- **WHEN** the user logs out
- **THEN** the app calls the backend logout endpoint, clears local session secrets, and returns to login

### Requirement: Refresh and expiry handling
The mobile app SHALL refresh expired sessions when backend refresh support is available and SHALL redirect to login when refresh fails.

#### Scenario: API request receives unauthorized
- **WHEN** an authenticated API request receives `401`
- **THEN** the app attempts one refresh request and retries the original request once if refresh succeeds

#### Scenario: Refresh fails
- **WHEN** refresh returns unauthorized or no valid refresh cookie/session exists
- **THEN** the app clears local auth state and requires login

### Requirement: Typed API contracts and errors
The mobile app SHALL parse backend responses into typed models based on `backend/openapi-schema.json` and SHALL present consistent loading, empty, error, and retry states.

#### Scenario: API response parse succeeds
- **WHEN** the backend returns a documented JSON response
- **THEN** repositories return typed app models to controllers/widgets

#### Scenario: API call fails
- **WHEN** a request fails due to network, auth, validation, or server error
- **THEN** the app displays a safe error message with retry where appropriate and does not log secrets
