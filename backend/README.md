# Backend Notes

## InsightFace smoke test

Run from `backend/` after installing dependencies:

```bash
python - <<'PY'
from pathlib import Path
from app.services.face_detection.service import detect_faces

faces = detect_faces(Path('/media/originals/path/to/image.jpg'))
print(f'faces={len(faces)}')
for face in faces:
    print(face.bounding_box, face.confidence, len(face.embedding))
PY
```

Notes:
- InsightFace weights are cached under `AI_CACHE_DIR/insightface`.
- This phase is inference-only and does not write `faces` rows.

## Person thumbnails

- Run migrations from `backend/`:
  - `alembic upgrade head`
- Person thumbnails are derived files stored under:
  - `generated/people/thumbnails/{person_id}.webp`
- They are served through the existing processed media mount:
  - `/media/processed/generated/people/thumbnails/{person_id}.webp`
- Verify thumbnail state in Postgres:

```sql
SELECT id, thumbnail_face_id, thumbnail_path, thumbnail_manually_set
FROM people
ORDER BY id;
```
