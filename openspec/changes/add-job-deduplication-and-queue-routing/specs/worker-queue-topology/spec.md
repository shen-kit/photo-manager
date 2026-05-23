## ADDED Requirements

### Requirement: Worker queues SHALL be separated by intent class
The system SHALL provide distinct ARQ queues for interactive, metadata, preview, AI, backfill, and maintenance work.

#### Scenario: Interactive queue exists
- **WHEN** user-triggered urgent preview or single-asset work is dispatched
- **THEN** the dispatcher can route it to `interactive`

#### Scenario: Backfill queue exists
- **WHEN** full-library CLIP, face, preview, thumbnail, or repair work is dispatched
- **THEN** the dispatcher can route it to `backfill`

### Requirement: Same task SHALL route differently by intent
The system SHALL allow identical underlying task functions to route to different queues depending on user intent or job origin.

#### Scenario: Preview route differs by intent
- **WHEN** preview generation is requested from asset-open interaction
- **THEN** it routes to `interactive`

#### Scenario: Preview route differs for background work
- **WHEN** preview generation is requested for ordinary asynchronous generation
- **THEN** it routes to `preview`

#### Scenario: Preview route differs for library repair
- **WHEN** preview generation is requested from full-library repair or backfill
- **THEN** it routes to `backfill`

### Requirement: Docker Compose SHALL define two worker roles
The system SHALL run two worker containers from the same Docker image with queue subscriptions and concurrency controlled by environment variables.

#### Scenario: Fast worker role
- **WHEN** Docker Compose starts the fast worker
- **THEN** it consumes `interactive`, `metadata`, and `preview`

#### Scenario: Batch worker role
- **WHEN** Docker Compose starts the batch worker
- **THEN** it consumes `ai`, `backfill`, and `maintenance`

### Requirement: Worker concurrency SHALL remain conservative
The initial worker topology SHALL favor responsiveness and host safety over throughput.

#### Scenario: Fast worker concurrency
- **WHEN** `worker-fast` starts
- **THEN** its concurrency is limited to approximately 1–2 task slots

#### Scenario: Batch worker concurrency
- **WHEN** `worker-batch` starts
- **THEN** its concurrency is limited to 1 task slot

### Requirement: Heavy job classes SHALL support serialization limits
The system SHALL enforce per-job-type execution limits when worker-level concurrency alone is insufficient to protect responsiveness and host stability.

#### Scenario: Video preview serialization
- **WHEN** multiple video preview jobs are available
- **THEN** no more than one video preview job runs at a time

#### Scenario: CLIP serialization
- **WHEN** multiple CLIP jobs are available
- **THEN** no more than one CLIP job runs at a time

#### Scenario: Face and clustering serialization
- **WHEN** face detection, face clustering, or scan jobs are available
- **THEN** each heavy job class obeys its configured single-job execution limit
