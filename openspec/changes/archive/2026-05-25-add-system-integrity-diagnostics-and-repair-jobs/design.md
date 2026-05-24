## Context

The backend already has a useful repair substrate: manual jobs, queue routing, asset-processing state, and several candidate queries for missing thumbnails, missing CLIP embeddings, and missing face processing. What is missing is a durable integrity layer that can run explicit snapshot checks, persist large result sets, present those results through an API, and drive repairs from the exact snapshot that the user reviewed.

This change must work for libraries with 50,000+ assets, so result storage, paging, and retention matter more than minimizing row counts at all costs. The current `/health` endpoint is intentionally tiny and should remain cheap; deep integrity checks belong in background jobs and cached results, not readiness probes.

## Goals / Non-Goals

**Goals:**
- Add a code-defined integrity diagnostics subsystem with explicit run semantics and cached snapshot results.
- Persist diagnostic run summaries and per-item findings so results are auditable, paginated, and reusable by repair jobs.
- Execute diagnostics through the existing job dispatcher with clear `diagnostic:` job key prefixes.
- Provide one repair action per supported diagnostic, driven by the persisted snapshot scope and live revalidation of each item.
- Retain only the last three runs per diagnostic and purge older child finding rows.
- Keep integrity logic maintainable by reusing existing query and repair services where possible.

**Non-Goals:**
- Expanding `/health` into a deep integrity endpoint.
- Running full-library integrity checks automatically on every page load.
- Supporting multiple repair actions per diagnostic in the first version.
- Providing automatic repair for missing originals in the first version.
- Making diagnostic definitions user-editable in the database.

## Decisions

### Use code-defined diagnostics with persisted runs and persisted item rows

The system will define diagnostics in code and persist execution state in two new tables:
- `diagnostic_runs` for run-level metadata, summary state, timestamps, and linked repair metadata.
- `diagnostic_run_items` for per-item findings such as affected asset IDs, person IDs, relative paths, reason codes, repairability, and small structured details.

Rationale:
- One large JSON blob per run would be difficult to page, difficult to consume for repairs, and brittle for large libraries.
- 50k+ finding rows per run are acceptable in Postgres when rows are narrow, keyed by run ID, and aggressively retained.
- Persisted item rows make repair scope deterministic and auditable.

Alternatives considered:
- Store all candidates in a JSONB array on `diagnostic_runs`. Rejected because paging, repair streaming, and retention cleanup become clumsy.
- Recompute candidates at repair time. Rejected because it breaks snapshot determinism and produces count drift.

### Run diagnostics and repairs through the existing job dispatcher

Diagnostic execution will use the same dispatcher and worker/job model as current background work. New job keys will use a `diagnostic:` prefix for clarity, while repair actions can continue to reuse existing repair job machinery where it already exists.

Rationale:
- Reuses queue routing, progress reporting, job history, auth patterns, and observability.
- Avoids introducing a second background execution stack.

Alternatives considered:
- Build a separate execution framework for diagnostics. Rejected because it duplicates existing job infrastructure without strong benefit.

### Keep `/health` cheap and expose integrity through dedicated APIs

The existing `/health` endpoint will remain a low-cost liveness/readiness response. Integrity state will be exposed through authenticated system integrity endpoints that return cached latest results and allow explicit run requests.

Rationale:
- Full-library scans are too expensive for readiness probes.
- Cached explicit diagnostics are a better operator experience for large libraries.

Alternatives considered:
- Expand `/health` to include integrity counts. Rejected because it conflates liveness with expensive diagnostics and encourages poor probe behavior.

### Use snapshot-driven repairs with live per-item revalidation

Repairs will always start from a persisted diagnostic run. Each item will be revalidated before any mutation. If an item is already healthy, the repair skips it; if still broken, the repair acts on it.

Rationale:
- Preserves deterministic user-reviewed scope while remaining safe when library state changes between diagnostic and repair time.

Alternatives considered:
- Repair exactly snapshot items with no revalidation. Rejected because it wastes work and causes avoidable failures on already-fixed items.
- Ignore snapshot scope and rerun the live diagnostic query. Rejected because it weakens auditability and causes confusing drift.

### Combine asset derivative checks into one richer diagnostic with one repair action

Derivative integrity will be exposed as one diagnostic, `check_asset_derivatives`, with subtype counts for missing `tiny`, `small`, `large`, and `video_preview` outputs. The repair surface will remain one action in v1.

Rationale:
- Users think in terms of “asset derivatives broken” more than separate internal file classes.
- One action keeps API and UI simpler while still exposing subtype detail in summaries.

Alternatives considered:
- One diagnostic per derivative subtype. Rejected because it adds noise without much operational value.

### Split orphan-file diagnostics into originals and processed files

Original files without DB assets and processed files without DB assets will be separate diagnostics.

Rationale:
- Detection logic, repair semantics, and risk profiles differ materially between originals and processed files.
- Splitting them keeps each diagnostic precise and maintainable.

Alternatives considered:
- One combined orphan-files diagnostic. Rejected because the categories have different operator meaning and different repair futures.

### Support detect-only diagnostics where repair semantics are unsafe or deferred

`check_originals_exist` will be detect-only in v1. `check_people_without_active_faces` will offer a repair action that deletes such people after revalidation. Other supported diagnostics will expose one repair action.

Rationale:
- Missing originals can represent multiple underlying causes and are not safe to auto-fix yet.
- People without active faces have a clear cleanup action already aligned with current data semantics.

Alternatives considered:
- Auto-repair missing originals through path relinking or deletion. Rejected as too risky for the first version.

### Retain only the last three runs per diagnostic

After completing a new run, the system will keep the newest three runs for that diagnostic and delete older runs along with their `diagnostic_run_items` rows.

Rationale:
- Keeps storage bounded even when large runs emit tens of thousands of rows.
- Matches operator need for recent history without indefinite growth.

Alternatives considered:
- Time-based retention only. Rejected because operator usage cadence may vary, making space use unpredictable.
- Keep many historical runs. Rejected because it adds storage churn without clear first-version value.

## Risks / Trade-offs

- [Filesystem scans on large libraries may take significant time] → Mitigation: run as background jobs only, paginate results, and surface cached snapshots instead of live scans.
- [`diagnostic_run_items` can grow quickly with repeated large scans] → Mitigation: keep rows narrow, index by run, and enforce “last three runs per diagnostic” retention.
- [Diagnostic logic can drift from repair logic] → Mitigation: centralize candidate detection paths and make repairs consume persisted snapshot scope rather than rerunning broad live queries.
- [Processed orphan detection may misclassify future generated files] → Mitigation: keep ownership/path rules explicit and constrain detection to known generated layouts in v1.
- [Outdated face and CLIP semantics depend on current default models] → Mitigation: define outdated state explicitly in terms of the current default model and reuse existing model-aware services.
- [Delete repair for people without active faces is destructive] → Mitigation: require explicit repair action, revalidate per item, and keep the diagnostic result visible before repair.
