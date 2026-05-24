## Why

The backend currently exposes manual repair jobs and a minimal `/health` endpoint, but it cannot capture a durable view of system integrity or drive repairs from a known diagnostic snapshot. As the library grows past tens of thousands of assets, operators need explicit, cached integrity checks with auditable results and deterministic repair scopes instead of ad-hoc manual backfills.

## What Changes

- Add a new system integrity diagnostics capability that lets authenticated users run explicit diagnostic snapshot jobs and review cached results.
- Persist diagnostic runs and per-item findings so large integrity scans can be paginated, audited, retained, and used as repair input.
- Add integrity diagnostics for missing originals, missing asset derivatives, missing or outdated CLIP embeddings, missing or outdated face processing, original files without DB assets, processed files without DB assets, and people without active faces.
- Add one repair action per supported diagnostic that reuses the persisted snapshot scope and live-revalidates each item before mutation.
- Keep `/health` focused on cheap liveness/readiness checks rather than full-library integrity scans.
- Route diagnostics through the existing job dispatcher using `diagnostic:` job key prefixes for clarity and observability.

## Capabilities

### New Capabilities
- `system-integrity-diagnostics`: Run cached integrity diagnostics, persist detailed findings, page through snapshot items, and trigger supported repair jobs from a recorded diagnostic run.

### Modified Capabilities

## Impact

- Affected code: new `system_integrity` service and API modules, job dispatch integration, manual repair job integration, and retention cleanup paths.
- Affected APIs: new authenticated endpoints for listing diagnostics, running diagnostics, viewing runs/items, and launching repairs from a snapshot.
- Affected data model: new persistence for diagnostic runs and per-item findings, plus retention cleanup for older snapshots.
- Affected systems: Postgres storage for diagnostic data, ARQ worker queues for diagnostic execution, filesystem scans for originals/processed-file diagnostics, and existing repair jobs for derivatives, embeddings, faces, and people cleanup.
