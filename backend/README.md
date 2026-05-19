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
