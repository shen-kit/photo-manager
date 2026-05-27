## ADDED Requirements

### Requirement: Per-asset processing SHALL use one shared DAG definition
The system SHALL define per-asset processing as a shared in-code DAG of coarse-grained capabilities rather than scattering follow-up dependency rules across feature services.

#### Scenario: Upload and scan share node semantics
- **WHEN** an uploaded asset and a scanned asset both require the same downstream work
- **THEN** the system evaluates them against the same node definitions and dependency rules
- **AND** only their scheduling policy may differ

#### Scenario: Restore reuses DAG evaluation
- **WHEN** a deleted asset is restored
- **THEN** the system re-evaluates the shared per-asset DAG
- **AND** queues only the nodes that are missing, stale, or retryable
- **AND** does not blindly replay all ingest follow-up work

### Requirement: DAG nodes SHALL be model-sensitive and dependency-aware
The system SHALL evaluate whether a node is applicable, complete, stale, retryable, or blocked by dependencies using durable asset state, derived files, `asset_processing`, and current model defaults.

#### Scenario: CLIP node becomes stale after default model change
- **WHEN** an asset has a stored CLIP vector for an older model
- **THEN** the `clip_embedding` node is treated as stale for the current default model
- **AND** the system schedules or reports work only for the current model id

#### Scenario: Video CLIP depends on derived image input
- **WHEN** the system evaluates CLIP processing for a video asset
- **THEN** it treats the required thumbnail or preview derivative as a dependency
- **AND** it does not treat the CLIP node as runnable until the dependency is satisfied

### Requirement: Per-asset DAG scheduling SHALL support multiple entry policies
The system SHALL support operation-specific entrypoints over the same DAG for upload, scan, restore, preview requests, CLIP backfills, face backfills, and per-asset repair flows.

#### Scenario: Preview request enters at preview node
- **WHEN** a client requests a preview for an asset
- **THEN** the system enters the DAG at the relevant preview node
- **AND** does not require unrelated nodes to be enqueued
- **AND** may still use the existing inline fast path when allowed

#### Scenario: Face backfill enters at face node
- **WHEN** a manual backfill requests face processing
- **THEN** the system enters at `face_processing`
- **AND** may optionally continue to `face_matching` according to policy
- **AND** uses the same stale and completion semantics as non-backfill flows

### Requirement: Manual and global workflows SHALL remain outside the per-asset DAG
The system SHALL keep global or cross-asset workflows as parent schedulers, diagnostics, or maintenance tasks rather than modeling them as ordinary per-asset DAG nodes.

#### Scenario: Face clustering remains global
- **WHEN** a user runs face clustering
- **THEN** the system treats clustering as a global or manual job
- **AND** does not require clustering to appear as a normal per-asset `asset_processing` node

#### Scenario: Backfill parent job aggregates many DAG runs
- **WHEN** a manual CLIP or face backfill schedules work for many assets
- **THEN** the parent job aggregates progress across those per-asset DAG outcomes
- **AND** remains distinct from the per-asset node records

### Requirement: DAG execution SHALL be idempotent and crash-recoverable
The system SHALL make node execution idempotent and SHALL recover from abandoned queued or running work without requiring manual database cleanup.

#### Scenario: Worker dies mid-node
- **WHEN** a worker dies after claiming a node but before completing it
- **THEN** later DAG evaluation detects the node as retryable after its job is no longer active or its lease expires
- **AND** the system can safely enqueue or run that node again

#### Scenario: Duplicate active work is suppressed
- **WHEN** an equivalent node execution is already active for the same asset, model, and parameters
- **THEN** the system reuses or suppresses the duplicate enqueue through shared dedupe semantics
- **AND** only explicit urgent or forced policy may bypass that suppression

### Requirement: Face reruns SHALL preserve manual decisions
The system SHALL preserve confirmed faces, exclusions, and manual person assignments when re-running face-related DAG nodes.

#### Scenario: Forced face processing preserves confirmed decisions
- **WHEN** face processing is forced for an asset that already contains confirmed or excluded faces
- **THEN** the system may rebuild disposable unconfirmed detections for the current model
- **AND** it does not delete or overwrite confirmed, excluded, or manually assigned decisions

#### Scenario: Incremental matching stays scoped
- **WHEN** the DAG runs `face_matching`
- **THEN** it operates only on eligible faces for the current model and policy
- **AND** it preserves manual overrides that already exist
