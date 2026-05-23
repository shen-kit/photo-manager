## ADDED Requirements

### Requirement: Worker-enqueued jobs SHALL use centralized dispatching
The system SHALL route worker-enqueued jobs through a central dispatching layer that decides queue selection, dedupe policy, and enqueue metadata instead of allowing services to hardcode queue names independently.

#### Scenario: Service enqueues preview work
- **WHEN** a service requests preview generation for an asset
- **THEN** the dispatcher chooses queue and dedupe behavior based on task and intent
- **AND** the service does not need to know concrete queue names

#### Scenario: Service enqueues CLIP work
- **WHEN** a service requests CLIP embedding generation
- **THEN** the dispatcher computes the dedupe key and target queue centrally

### Requirement: Active semantic dedupe SHALL be global across queues
The system SHALL prevent duplicate active work for equivalent semantic jobs across all worker queues unless bypass behavior is explicitly requested.

#### Scenario: Reuse active duplicate in another queue
- **WHEN** an active CLIP job already exists for the same asset, model, and params
- **AND** another non-forced enqueue request arrives for that same semantic work
- **THEN** the dispatcher does not enqueue another active duplicate

#### Scenario: Dedupe key includes model-sensitive work
- **WHEN** CLIP work is requested for same asset but a different model id
- **THEN** the dispatcher treats it as distinct semantic work

### Requirement: Deterministic dedupe keys SHALL exist for asset-specific jobs
The system SHALL compute deterministic dedupe keys for asset-specific jobs using task identity and relevant asset/model/parameter fields.

#### Scenario: Preview key
- **WHEN** preview generation is enqueued for an asset
- **THEN** the dedupe key is stable for that asset preview work

#### Scenario: Face processing key
- **WHEN** face processing is enqueued for an asset with a specific model and `auto_match` setting
- **THEN** the dedupe key changes when model or `auto_match` changes

### Requirement: Force bypass SHALL ignore dedupe for supported jobs
Jobs that support `force=true` SHALL be allowed to bypass semantic dedupe and enqueue new work intentionally.

#### Scenario: Force CLIP rebuild
- **WHEN** CLIP embedding generation is requested with `force=true`
- **THEN** the dispatcher enqueues new work even if equivalent active work exists

### Requirement: Urgent intent SHALL allow explicit duplicate enqueue
The dispatcher SHALL allow urgent user-triggered work to enqueue a duplicate active job when responsiveness is more important than reusing lower-priority background work.

#### Scenario: User requests preview while backfill preview is already active
- **WHEN** a backfill preview job is already active for an asset
- **AND** the user opens that asset and requests an urgent preview
- **THEN** the dispatcher may enqueue an urgent duplicate preview job
- **AND** the urgent duplicate is routed to the interactive lane

### Requirement: Enqueue metadata SHALL be recorded on jobs
The system SHALL persist queue and dedupe metadata on job records for observability and dedupe lookup.

#### Scenario: Job row stores queue and dedupe information
- **WHEN** dispatcher creates a new job row
- **THEN** the row includes its queue assignment and semantic dedupe metadata
