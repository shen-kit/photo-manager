Run Alembic from the `backend/` directory.

- Create revision: `alembic revision --autogenerate -m "describe change"`
- Apply latest: `alembic upgrade head`
- Show current revision: `alembic current`
- Verify model/schema sync: `alembic check`
- Fresh local DB from migrations: create the database, then run `alembic upgrade head`
- Start API/worker only after `alembic upgrade head` succeeds
- Existing local DB created outside Alembic: reset it and run `alembic upgrade head`
- `alembic upgrade head` also seeds `ai_models` idempotently for OpenCLIP and InsightFace
- Verify seed rows: `SELECT id, model_name, version_tag, vector_dimensions FROM ai_models ORDER BY id;`
- Verify default CLIP model:
  `SELECT d.task, d.model_id, m.model_name, m.version_tag, m.vector_dimensions, m.is_deprecated FROM ai_model_defaults d JOIN ai_models m ON m.id = d.model_id WHERE d.task = 'clip_embedding';`
- Install CLIP dependencies: `pip install -r requirements.txt`
- Backfill embeddings for existing assets: `python scripts/backfill_clip_embeddings.py`
- Force-regenerate embeddings: `python scripts/backfill_clip_embeddings.py --force`
- Search endpoint: `GET /api/v1/search?query=golden+retriever&limit=25`
- Verify asset embeddings: `SELECT id, search_model_id, search_vector IS NOT NULL AS has_embedding FROM assets ORDER BY created_at DESC LIMIT 20;`

Notes:

- `DATABASE_URL` is read from the backend environment, matching app runtime config.
- Application startup does not run migrations or call `create_all()`. Schema changes must go through Alembic.
- `ai_models` stores versioned model records by task; `ai_model_defaults` selects the active model per task.
- Face recognition default model:
  `SELECT d.task, d.model_id, m.model_name, m.version_tag, m.vector_dimensions, m.is_deprecated FROM ai_model_defaults d JOIN ai_models m ON m.id = d.model_id WHERE d.task = 'face_recognition';`
- `faces` stores face-detection metadata separately from CLIP search embeddings, including bounding box JSON, optional face embedding, the producing `face_model_id`, and manual-review flags.
- The seeded InsightFace `buffalo_l` registry entry is metadata only in this phase. InsightFace model packs are research/non-commercial use; verify license terms before enabling inference.
- The first CLIP embedding run will download OpenCLIP weights if they are not already cached.
