# Repository Guidelines

## Project Structure & Module Organization
This repository currently centers on the FastAPI backend in `backend/`. Application code lives in `backend/app/`:
- `api/v1/features/`: feature-first HTTP endpoints such as `assets.py` and `auth.py`
- `core/`: shared infrastructure such as auth, database, and security helpers
- `services/`: background or domain logic, for example asset metadata jobs
- `models.py`: shared SQLModel database and response models

Persistent runtime data is kept outside the app code:
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
- `just docs`: print the Swagger docs URL
- `just register` / `just login`: bootstrap and test auth flows
- `python -m compileall backend/app backend/worker.py`: fast syntax check before committing

## Coding Style & Naming Conventions
Target Python 3.11+ and keep code strongly typed. Follow existing conventions:
- 4-space indentation, `snake_case` for functions/variables, `PascalCase` for SQLModel classes
- keep new endpoints under `backend/app/api/v1/features/`
- prefer shared logic in `services/` over large route handlers
- store media paths relative to the library root, not absolute host paths

No formatter or linter is configured yet. Match the surrounding style and keep route responses explicit with Pydantic/SQLModel models.

## Testing Guidelines
There is no committed pytest suite yet. For now:
- run `python -m compileall backend/app backend/worker.py`
- exercise the API via `just register`, `just login`, `just assets`, or `/docs`
- validate schema changes against a real Postgres container, especially `SQLModel` field additions

When adding tests later, prefer `test_<feature>.py` naming and keep API tests close to the backend feature they cover.

## Commit & Pull Request Guidelines
Recent commits use short imperative subjects, for example `Create basic asset CRUD`. Follow that pattern.

PRs should include:
- a concise summary of behavior changes
- any required env, schema, or storage changes
- manual verification steps or example API calls
- screenshots only when UI work exists

## Security & Configuration Tips
Keep secrets in the repo-root `.env` only. Do not commit JWT secrets, cookies, or media files. Preserve the rule that originals are never deleted or modified by API code.
