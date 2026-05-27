from __future__ import annotations

from dataclasses import dataclass

# Keep task identifiers centralized so queueing, tracker state, and
# policy decisions stay aligned across services and migrations.
NODE_METADATA_REFRESH = "metadata_refresh"
NODE_TINY_THUMBNAIL = "tiny_thumbnail"
NODE_SMALL_THUMBNAIL = "small_thumbnail"
NODE_IMAGE_PREVIEW = "image_preview"
NODE_VIDEO_PREVIEW = "video_preview"
NODE_CLIP_EMBEDDING = "clip_embedding"
NODE_FACE_PROCESSING = "face_recognition"
NODE_FACE_MATCHING = "face_matching"


@dataclass(frozen=True)
class ProcessingNodeDefinition:
    task: str
    base_dependencies: tuple[str, ...] = ()
    model_sensitive: bool = False
    description: str = ""


NODE_DEFINITIONS: dict[str, ProcessingNodeDefinition] = {
    NODE_METADATA_REFRESH: ProcessingNodeDefinition(
        task=NODE_METADATA_REFRESH,
        description="Refresh asset metadata and timeline fields.",
    ),
    NODE_TINY_THUMBNAIL: ProcessingNodeDefinition(
        task=NODE_TINY_THUMBNAIL,
        base_dependencies=(NODE_METADATA_REFRESH,),
        description="Generate the tiny derived thumbnail.",
    ),
    NODE_SMALL_THUMBNAIL: ProcessingNodeDefinition(
        task=NODE_SMALL_THUMBNAIL,
        base_dependencies=(NODE_METADATA_REFRESH,),
        description="Generate the small derived thumbnail.",
    ),
    NODE_IMAGE_PREVIEW: ProcessingNodeDefinition(
        task=NODE_IMAGE_PREVIEW,
        base_dependencies=(NODE_METADATA_REFRESH,),
        description="Generate the large image preview.",
    ),
    NODE_VIDEO_PREVIEW: ProcessingNodeDefinition(
        task=NODE_VIDEO_PREVIEW,
        base_dependencies=(NODE_METADATA_REFRESH,),
        description="Generate the transcoded video preview.",
    ),
    NODE_CLIP_EMBEDDING: ProcessingNodeDefinition(
        task=NODE_CLIP_EMBEDDING,
        base_dependencies=(NODE_METADATA_REFRESH,),
        model_sensitive=True,
        description="Generate the current CLIP embedding.",
    ),
    NODE_FACE_PROCESSING: ProcessingNodeDefinition(
        task=NODE_FACE_PROCESSING,
        base_dependencies=(NODE_METADATA_REFRESH,),
        model_sensitive=True,
        description="Run face detection and persist current-model faces.",
    ),
    NODE_FACE_MATCHING: ProcessingNodeDefinition(
        task=NODE_FACE_MATCHING,
        base_dependencies=(NODE_FACE_PROCESSING,),
        description="Run incremental face matching and people maintenance.",
    ),
}


def get_node_definition(task: str) -> ProcessingNodeDefinition:
    try:
        return NODE_DEFINITIONS[task]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(f"Unsupported processing DAG node: {task}") from exc
