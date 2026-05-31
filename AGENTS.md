# Repository Guidelines


## Project Structure & Module Organization
This repository currently centers on the FastAPI backend in `backend/`. Application code lives in `backend/app/`:
- `api/v1/features/`: feature-first HTTP endpoints such as `assets.py` and `auth.py`
- `core/`: shared infrastructure such as auth, database, and security helpers
- `services/`: background or domain logic, for example asset metadata jobs
- `models.py`: shared SQLModel database and response models

Persistent runtime data is kept outside the app code. Never directly edit this:
- `storage/originals/`: source media, treated as read-only
- `storage/processed/`: generated thumbnails and previews
- `data/`: Redis and AI cache state

## Build, Test, and Development Commands
Use `just` targets from the repo root:
- `just up`: build and start the full Docker stack
- `just up-d`: start detached
- `just down`: stop containers
- `just logs api`: follow service logs
- `just health`: check the API health endpoint
- `python -m compileall backend/app backend/worker.py`: fast syntax check before committing
- `just openapi-check`: validate openapi schema is consistent with backend
- `just openapi`: regenerate the openapi schema if outdated or changes are made

- Always use backend/.venv/bin/python when working in the backend. Do not default to global system python commands.
- 
## Coding Style & Naming Conventions
Target Python 3.11+ and keep code strongly typed. Follow existing conventions:
- 4-space indentation, `snake_case` for functions/variables, `PascalCase` for SQLModel classes
- keep new endpoints under `backend/app/api/v1/features/`
- prefer shared logic in `services/` over large route handlers
- store media paths relative to the library root, not absolute host paths
- to format the Python files: use `ruff format backend`

## Commit & Pull Request Guidelines

- Commit message: Use short imperative subjects, e.g. `Create basic asset CRUD`.
- description should be a dot-point list, containing in order:
    1. overall commit objective + changed functionality
    2. high-level code/architecture changes
    3. key details/design decisions

## Security & Configuration Tips
Keep secrets in the repo-root `.env` only. Do not commit JWT secrets, cookies, or media files. Preserve the rule that originals are never deleted or modified by API code.

# OpenSpec workflow

For non-trivial features, architecture changes, refactors, database migrations, or behaviour changes:

1. Use `openspec-explore` first to inspect existing specs and code.
2. Use `openspec-propose` to create or update the change proposal.
3. Do not implement until the proposal/spec/tasks are reviewed or clearly accepted.
4. Use `openspec-apply` to implement approved tasks.
5. Run `openspec validate` before considering the change complete.
6. Ask before archiving unless I explicitly request archive.
