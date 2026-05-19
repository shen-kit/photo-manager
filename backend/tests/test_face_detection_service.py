from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.services.face_detection.service import (
    FACE_MODEL_NAME,
    DetectedFace,
    FaceDetectionFileNotFoundError,
    FaceDetectionService,
    FaceDetectionUnreadableImageError,
    FaceDetectionUnsupportedMediaError,
)


class FaceDetectionServiceTest(unittest.TestCase):
    def test_detect_faces_returns_oriented_pixel_boxes_embeddings_and_landmarks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "portrait.jpg"
            Image.new("RGB", (100, 60), color="white").save(image_path)

            raw_face = SimpleNamespace(
                bbox=np.array([10.2, 5.4, 70.8, 45.1], dtype=np.float32),
                det_score=0.987,
                embedding=np.arange(512, dtype=np.float32),
                kps=np.array([[15.0, 10.0], [60.0, 10.0]], dtype=np.float32),
            )
            runtime = SimpleNamespace(
                analyzer=SimpleNamespace(get=lambda image: [raw_face])
            )
            service = FaceDetectionService(model_name=FACE_MODEL_NAME)

            with patch(
                "app.services.face_detection.service.get_face_runtime",
                return_value=runtime,
            ):
                detected = service.detect_faces(image_path)

        self.assertEqual(len(detected), 1)
        face = detected[0]
        self.assertIsInstance(face, DetectedFace)
        self.assertEqual(face.bounding_box.x, 10)
        self.assertEqual(face.bounding_box.y, 5)
        self.assertEqual(face.bounding_box.width, 61)
        self.assertEqual(face.bounding_box.height, 41)
        self.assertEqual(face.bounding_box.image_width, 100)
        self.assertEqual(face.bounding_box.image_height, 60)
        self.assertAlmostEqual(face.confidence, 0.987)
        self.assertEqual(len(face.embedding), 512)
        self.assertEqual(face.embedding[0], 0.0)
        self.assertEqual(face.embedding[-1], 511.0)
        self.assertIsNotNone(face.landmarks)
        assert face.landmarks is not None
        self.assertEqual(len(face.landmarks), 2)
        self.assertEqual(face.landmarks[0].x, 15.0)
        self.assertEqual(face.landmarks[0].y, 10.0)

    def test_detect_faces_returns_empty_list_when_no_faces_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "empty.jpg"
            Image.new("RGB", (40, 30), color="white").save(image_path)
            runtime = SimpleNamespace(analyzer=SimpleNamespace(get=lambda image: []))
            service = FaceDetectionService()

            with patch(
                "app.services.face_detection.service.get_face_runtime",
                return_value=runtime,
            ):
                detected = service.detect_faces(image_path)

        self.assertEqual(detected, [])

    def test_detect_faces_rejects_missing_files(self) -> None:
        service = FaceDetectionService()
        with self.assertRaises(FaceDetectionFileNotFoundError):
            service.detect_faces(Path("/tmp/does-not-exist.jpg"))

    def test_detect_faces_rejects_unsupported_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "note.txt"
            image_path.write_text("not an image", encoding="utf-8")
            service = FaceDetectionService()

            with self.assertRaises(FaceDetectionUnsupportedMediaError):
                service.detect_faces(image_path)

    def test_detect_faces_rejects_unreadable_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "broken.jpg"
            image_path.write_bytes(b"not really a jpeg")
            service = FaceDetectionService()

            with self.assertRaises(FaceDetectionUnreadableImageError):
                service.detect_faces(image_path)


if __name__ == "__main__":
    unittest.main()
