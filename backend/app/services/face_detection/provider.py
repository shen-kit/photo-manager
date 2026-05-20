from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from app.services.face_detection.service import (
    DetectedFace,
    FaceDetectionService,
)


class FaceDetectionProvider(Protocol):
    def detect_faces(self, image_path: Path) -> list[DetectedFace]: ...


class InsightFaceDetectionProvider:
    def __init__(self, *, service: FaceDetectionService | None = None) -> None:
        self.service = service or FaceDetectionService()

    def detect_faces(self, image_path: Path) -> list[DetectedFace]:
        return self.service.detect_faces(image_path)


class CallableFaceDetectionProvider:
    def __init__(self, detector: Callable[[Path], list[DetectedFace]]) -> None:
        self.detector = detector

    def detect_faces(self, image_path: Path) -> list[DetectedFace]:
        return self.detector(image_path)


def resolve_face_detection_provider(
    provider: FaceDetectionProvider | Callable[[Path], list[DetectedFace]] | None,
) -> FaceDetectionProvider:
    if provider is None:
        return InsightFaceDetectionProvider()
    if hasattr(provider, "detect_faces"):
        return cast(FaceDetectionProvider, provider)
    return CallableFaceDetectionProvider(
        cast(Callable[[Path], list[DetectedFace]], provider)
    )
