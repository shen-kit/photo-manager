from __future__ import annotations

import os
from contextlib import nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import torch

AI_CACHE_DIR = Path(os.getenv("AI_CACHE_DIR", "/tmp/ai-cache")).resolve()
HF_HOME_DIR = AI_CACHE_DIR / "huggingface"
TORCH_HOME_DIR = AI_CACHE_DIR / "torch"
OPEN_CLIP_CACHE_DIR = AI_CACHE_DIR / "open_clip"

# These cache env vars need to exist before OpenCLIP/Hugging Face modules initialize.
os.environ.setdefault("HF_HOME", str(HF_HOME_DIR))
os.environ.setdefault("HF_HUB_CACHE", str(HF_HOME_DIR / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_HOME_DIR / "transformers"))
os.environ.setdefault("TORCH_HOME", str(TORCH_HOME_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(AI_CACHE_DIR))

from PIL import Image, ImageOps, UnidentifiedImageError

CLIP_DEVICE_PREFERENCE = os.getenv("CLIP_DEVICE", "auto").strip().lower()

OPENCLIP_ARCHITECTURE_BY_MODEL_NAME = {
    "openclip-vit-b-32": "ViT-B-32",
}


class ClipEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClipRuntime:
    model: Any
    preprocess: object
    tokenizer: object
    device: str


def _resolve_device() -> str:
    import torch

    if CLIP_DEVICE_PREFERENCE in {"cpu", "cuda"}:
        if CLIP_DEVICE_PREFERENCE == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return CLIP_DEVICE_PREFERENCE
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_openclip_architecture(model_name: str) -> str:
    architecture = OPENCLIP_ARCHITECTURE_BY_MODEL_NAME.get(model_name)
    if architecture is None:
        raise ClipEmbeddingError(f"Unsupported CLIP model {model_name}")
    return architecture


def _ensure_cache_environment() -> str:
    for path in (AI_CACHE_DIR, HF_HOME_DIR, TORCH_HOME_DIR, OPEN_CLIP_CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return str(OPEN_CLIP_CACHE_DIR)


@lru_cache(maxsize=8)
def get_clip_runtime(model_name: str, pretrained: str) -> ClipRuntime:
    import open_clip

    device = _resolve_device()
    architecture = resolve_openclip_architecture(model_name)
    cache_dir = _ensure_cache_environment()
    model, _, preprocess = open_clip.create_model_and_transforms(
        architecture,
        pretrained=pretrained,
        cache_dir=cache_dir,
    )
    model.eval()
    model.to(device)
    tokenizer = open_clip.get_tokenizer(architecture)
    return ClipRuntime(
        model=model,
        preprocess=preprocess,
        tokenizer=tokenizer,
        device=device,
    )


def _normalize_embedding(
    tensor: "torch.Tensor", *, expected_dimensions: int | None
) -> list[float]:
    normalized = tensor / tensor.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    embedding = normalized[0].detach().cpu().tolist()
    if expected_dimensions is not None and len(embedding) != expected_dimensions:
        raise ClipEmbeddingError(
            f"Expected {expected_dimensions} embedding dimensions, got {len(embedding)}"
        )
    return [float(value) for value in embedding]


def embed_image(
    path: Path,
    *,
    model_name: str,
    pretrained: str,
    expected_dimensions: int | None,
) -> list[float]:
    import torch

    runtime = get_clip_runtime(model_name, pretrained)
    try:
        with Image.open(path) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            image_input = runtime.preprocess(normalized).unsqueeze(0).to(runtime.device)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        raise ClipEmbeddingError(f"Unable to read image at {path}") from exc

    autocast_context = (
        torch.autocast(device_type="cuda")
        if runtime.device == "cuda"
        else nullcontext()
    )
    with torch.inference_mode(), autocast_context:
        features = runtime.model.encode_image(image_input)
    return _normalize_embedding(features, expected_dimensions=expected_dimensions)


def embed_text(
    query: str,
    *,
    model_name: str,
    pretrained: str,
    expected_dimensions: int | None,
) -> list[float]:
    import torch

    runtime = get_clip_runtime(model_name, pretrained)
    text_input = runtime.tokenizer([query]).to(runtime.device)
    autocast_context = (
        torch.autocast(device_type="cuda")
        if runtime.device == "cuda"
        else nullcontext()
    )
    with torch.inference_mode(), autocast_context:
        features = runtime.model.encode_text(text_input)
    return _normalize_embedding(features, expected_dimensions=expected_dimensions)
