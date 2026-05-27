from __future__ import annotations

from dataclasses import dataclass

from app.services.jobs.dispatcher import (
    INTENT_AI,
    INTENT_BACKFILL,
    INTENT_METADATA,
    INTENT_PREVIEW,
)


@dataclass(frozen=True)
class ProcessingPolicy:
    name: str
    intent: str
    force: bool = False
    auto_match: bool = False
    priority: str = "low"
    enqueue_embedding: bool = True
    enqueue_faces: bool = True


UPLOAD_POLICY = ProcessingPolicy(
    name="upload",
    intent=INTENT_METADATA,
    enqueue_embedding=True,
    enqueue_faces=True,
)
SCAN_POLICY = ProcessingPolicy(
    name="scan",
    intent=INTENT_BACKFILL,
    enqueue_embedding=True,
    enqueue_faces=True,
)
RESTORE_POLICY = ProcessingPolicy(
    name="restore",
    intent=INTENT_METADATA,
    enqueue_embedding=True,
    enqueue_faces=True,
    auto_match=True,
)
PREVIEW_POLICY = ProcessingPolicy(
    name="preview",
    intent=INTENT_PREVIEW,
    priority="low",
    enqueue_embedding=False,
    enqueue_faces=False,
)
CLIP_BACKFILL_POLICY = ProcessingPolicy(
    name="clip_backfill",
    intent=INTENT_BACKFILL,
    enqueue_embedding=True,
    enqueue_faces=False,
)
FACE_BACKFILL_POLICY = ProcessingPolicy(
    name="face_backfill",
    intent=INTENT_BACKFILL,
    enqueue_embedding=False,
    enqueue_faces=True,
)
CLIP_RUNTIME_POLICY = ProcessingPolicy(
    name="clip_runtime",
    intent=INTENT_AI,
    enqueue_embedding=True,
    enqueue_faces=False,
)
FACE_RUNTIME_POLICY = ProcessingPolicy(
    name="face_runtime",
    intent=INTENT_AI,
    enqueue_embedding=False,
    enqueue_faces=True,
)
