Run Alembic from the `backend/` directory.

- Create revision: `alembic revision --autogenerate -m "describe change"`
- Apply latest: `alembic upgrade head`
- Show current revision: `alembic current`
- Verify model/schema sync: `alembic check`
- Fresh local DB from migrations: create the database, then run `alembic upgrade head`
- Start API/worker only after `alembic upgrade head` succeeds
- Existing local DB created outside Alembic: reset it and run `alembic upgrade head`

Notes:

- `DATABASE_URL` is read from the backend environment, matching app runtime config.
- Application startup does not run migrations or call `create_all()`. Schema changes must go through Alembic.
