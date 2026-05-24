## ADDED Requirements

### Requirement: Users can run persisted integrity diagnostics on demand
The system SHALL expose authenticated integrity diagnostics that run only when explicitly requested, execute as background jobs through the existing dispatcher, and persist a snapshot result for later review.

#### Scenario: User requests a diagnostic run
- **WHEN** an authenticated user triggers a supported integrity diagnostic
- **THEN** the system creates a new diagnostic run record with queued job state
- **AND** dispatches a background job with a `diagnostic:` job key prefix
- **AND** returns a reference that can be used to inspect the run later

#### Scenario: Diagnostic run completes
- **WHEN** a diagnostic job finishes successfully
- **THEN** the system stores a completed diagnostic run with checked timestamps, health state, and summary data
- **AND** the latest cached result for that diagnostic becomes available through the integrity API

### Requirement: Diagnostic findings are persisted as paginated snapshot items
The system SHALL persist per-item findings for each diagnostic run so large result sets can be paginated, audited, retained, and reused by repairs.

#### Scenario: Large diagnostic emits many findings
- **WHEN** a diagnostic run identifies many affected assets, people, or paths
- **THEN** the system stores each finding as a diagnostic run item linked to the run
- **AND** each item includes the relevant identifier fields, a reason code, and whether it is repairable
- **AND** clients can retrieve items through paginated APIs without loading the full result set at once

#### Scenario: Diagnostic has no findings
- **WHEN** a diagnostic run finds no integrity issues
- **THEN** the system stores a completed run with healthy status
- **AND** the run has zero diagnostic run items

### Requirement: The system supports defined integrity diagnostics
The system SHALL provide code-defined diagnostics for missing originals, asset derivatives, CLIP embedding integrity, face processing integrity, original files without DB assets, processed files without DB assets, and people without active faces.

#### Scenario: Asset derivative diagnostic reports subtype counts
- **WHEN** the asset derivative diagnostic runs
- **THEN** the system evaluates missing `tiny`, `small`, `large`, and `video_preview` outputs as one diagnostic
- **AND** the stored summary includes subtype counts for each derivative class

#### Scenario: Model-sensitive diagnostics detect outdated work
- **WHEN** the CLIP embedding or face processing diagnostic runs
- **THEN** the system evaluates missing work and outdated work against the current default model for that task
- **AND** includes stale tracker or failed-processing conditions in the diagnostic result when relevant

#### Scenario: Detect-only diagnostic is reported
- **WHEN** the missing originals diagnostic runs
- **THEN** the system reports affected items and reasons
- **AND** does not expose a repair action for that diagnostic run

### Requirement: Repairs run from a persisted diagnostic snapshot
The system SHALL allow supported diagnostics to expose one repair action that uses the persisted snapshot as scope and revalidates each item before mutation.

#### Scenario: User starts a repair from a diagnostic run
- **WHEN** an authenticated user requests repair for a supported diagnostic run
- **THEN** the system creates a repair job linked to that diagnostic run
- **AND** the repair processes only items from that persisted run

#### Scenario: Repair revalidates items before acting
- **WHEN** a repair job processes a persisted diagnostic item
- **THEN** the system rechecks whether the item is still broken
- **AND** skips the item if it is already healthy
- **AND** performs the repair only if the item still needs action

#### Scenario: Detect-only diagnostic does not offer repair
- **WHEN** a user views a completed `check_originals_exist` run
- **THEN** the system shows the diagnostic result
- **AND** does not allow a repair action to be launched from that run

#### Scenario: People without active faces can be cleaned up
- **WHEN** a repair is launched from a `check_people_without_active_faces` run
- **THEN** the system deletes only people that still have no active faces after revalidation

### Requirement: Integrity snapshot retention is bounded
The system SHALL retain only the last three runs per diagnostic and purge older finding rows with their parent runs.

#### Scenario: New run exceeds retention limit
- **WHEN** a new completed or failed run causes a diagnostic to have more than three retained runs
- **THEN** the system deletes the oldest excess runs for that diagnostic
- **AND** deletes their associated diagnostic run items

### Requirement: Integrity APIs remain separate from cheap health checks
The system SHALL keep deep integrity reporting separate from the minimal health endpoint.

#### Scenario: Health probe requests liveness
- **WHEN** a caller requests `/health`
- **THEN** the system responds without running full-library integrity scans
- **AND** the response does not depend on recalculating diagnostic findings

#### Scenario: Client needs integrity status
- **WHEN** a client requests integrity status or run details
- **THEN** the system serves cached diagnostic runs and paginated findings through dedicated authenticated integrity endpoints
