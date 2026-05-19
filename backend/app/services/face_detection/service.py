from __future__ import annotations

import importlib
import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.assets.media import guess_mime_type, is_supported_image_mime_type

logger = logging.getLogger(__name__)

AI_CACHE_DIR = Path(os.getenv("AI_CACHE_DIR", "/tmp/ai-cache")).resolve()
INSIGHTFACE_HOME_DIR = AI_CACHE_DIR / "insightface"
FACE_MODEL_NAME = "buffalo_l"
FACE_MODEL_DIMENSIONS = 512
FACE_DETECTION_SIZE = (640, 640)
FACE_PROVIDER_ENV = "INSIGHTFACE_EXECUTION_PROVIDERS"


class FaceDetectionError(RuntimeError):
    pass


class FaceDetectionFileNotFoundError(FaceDetectionError):
    pass


class FaceDetectionUnsupportedMediaError(FaceDetectionError):
    pass


class FaceDetectionUnreadableImageError(FaceDetectionError):
    pass


@dataclass(frozen=True)
class FaceBoundingBox:
    x: int
    y: int
    width: int
    height: int
    image_width: int
    image_height: int


@dataclass(frozen=True)
class FaceLandmark:
    x: float
    y: float


@dataclass(frozen=True)
class DetectedFace:
    bounding_box: FaceBoundingBox
    confidence: float
    embedding: list[float]
    landmarks: list[FaceLandmark] | None = None


@dataclass(frozen=True)
class InsightFaceRuntime:
    analyzer: Any
    providers: tuple[str, ...]
    det_size: tuple[int, int]


def _resolve_providers() -> tuple[str, ...]:
    raw = os.getenv(FACE_PROVIDER_ENV, "").strip()
    if not raw:
        return ("CPUExecutionProvider",)
    providers = tuple(
        provider.strip() for provider in raw.split(",") if provider.strip()
    )
    return providers or ("CPUExecutionProvider",)


def _resolve_ctx_id(providers: tuple[str, ...]) -> int:
    if any("CUDAExecutionProvider" == provider for provider in providers):
        return 0
    return -1


def _ensure_cache_environment() -> Path:
    INSIGHTFACE_HOME_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("INSIGHTFACE_HOME", str(INSIGHTFACE_HOME_DIR))
    return INSIGHTFACE_HOME_DIR


@lru_cache(maxsize=4)
def get_face_runtime(
    model_name: str = FACE_MODEL_NAME,
    providers: tuple[str, ...] | None = None,
) -> InsightFaceRuntime:
    active_providers = providers or _resolve_providers()
    root_dir = _ensure_cache_environment()

    try:
        face_analysis_module = importlib.import_module("insightface.app")
    except ImportError as exc:  # pragma: no cover - depends on optional runtime deps
        raise FaceDetectionError("InsightFace dependencies are not installed") from exc

    analyzer = face_analysis_module.FaceAnalysis(
        name=model_name,
        root=str(root_dir),
        providers=list(active_providers),
    )
    analyzer.prepare(
        ctx_id=_resolve_ctx_id(active_providers), det_size=FACE_DETECTION_SIZE
    )
    logger.info(
        "Initialized InsightFace runtime",
        extra={"model_name": model_name, "providers": list(active_providers)},
    )
    return InsightFaceRuntime(
        analyzer=analyzer,
        providers=active_providers,
        det_size=FACE_DETECTION_SIZE,
    )


def _load_oriented_rgb_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as image:
            return ImageOps.exif_transpose(image).convert("RGB")
    except FileNotFoundError as exc:
        raise FaceDetectionFileNotFoundError(
            f"Image file was not found: {path}"
        ) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise FaceDetectionUnreadableImageError(
            f"Unable to read image at {path}"
        ) from exc


def _validate_supported_image_path(path: Path) -> None:
    if not path.is_file():
        raise FaceDetectionFileNotFoundError(f"Image file was not found: {path}")
    mime_type = guess_mime_type(path)
    if not is_supported_image_mime_type(mime_type):
        raise FaceDetectionUnsupportedMediaError(
            f"Unsupported media type for face detection: {mime_type}"
        )


def _to_bgr_array(image: Image.Image) -> np.ndarray:
    rgb_array = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgb_array[:, :, ::-1])


def _normalize_embedding(embedding: Any) -> list[float]:
    array = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if array.size != FACE_MODEL_DIMENSIONS:
        raise FaceDetectionError(
            f"Expected {FACE_MODEL_DIMENSIONS} embedding dimensions, got {array.size}"
        )
    return [float(value) for value in array.tolist()]


def _clamp_face_bbox(
    bbox: Any,
    *,
    image_width: int,
    image_height: int,
) -> FaceBoundingBox:
    values = np.asarray(bbox, dtype=np.float32).reshape(-1)
    if values.size < 4:
        raise FaceDetectionError("Face detector returned an invalid bounding box")

    x1 = max(0, min(int(math.floor(float(values[0]))), image_width))
    y1 = max(0, min(int(math.floor(float(values[1]))), image_height))
    x2 = max(x1, min(int(math.ceil(float(values[2]))), image_width))
    y2 = max(y1, min(int(math.ceil(float(values[3]))), image_height))
    return FaceBoundingBox(
        x=x1,
        y=y1,
        width=x2 - x1,
        height=y2 - y1,
        image_width=image_width,
        image_height=image_height,
    )


def _extract_landmarks(landmarks: Any) -> list[FaceLandmark] | None:
    if landmarks is None:
        return None
    points = np.asarray(landmarks, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] < 2:
        return None
    return [FaceLandmark(x=float(point[0]), y=float(point[1])) for point in points]


class FaceDetectionService:
    def __init__(self, *, model_name: str = FACE_MODEL_NAME) -> None:
        self.model_name = model_name

    def detect_faces(self, image_path: Path) -> list[DetectedFace]:
        path = Path(image_path)
        _validate_supported_image_path(path)
        image = _load_oriented_rgb_image(path)
        image_width, image_height = image.size
        runtime = get_face_runtime(self.model_name)
        bgr_image = _to_bgr_array(image)

        try:
            raw_faces = runtime.analyzer.get(bgr_image)
        except Exception as exc:  # pragma: no cover - depends on native runtime
            raise FaceDetectionError(
                f"InsightFace detection failed for {path}"
            ) from exc

        detected_faces: list[DetectedFace] = []
        for raw_face in raw_faces:
            bounding_box = _clamp_face_bbox(
                getattr(raw_face, "bbox", None),
                image_width=image_width,
                image_height=image_height,
            )
            detected_faces.append(
                DetectedFace(
                    bounding_box=bounding_box,
                    confidence=float(getattr(raw_face, "det_score", 0.0)),
                    embedding=_normalize_embedding(
                        getattr(raw_face, "embedding", None)
                    ),
                    landmarks=_extract_landmarks(getattr(raw_face, "kps", None)),
                )
            )

        logger.debug(
            "Detected faces in image",
            extra={"image_path": str(path), "face_count": len(detected_faces)},
        )
        return detected_faces


def detect_faces(image_path: Path) -> list[DetectedFace]:
    service = FaceDetectionService()
    return service.detect_faces(image_path)
