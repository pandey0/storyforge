"""
Scored image-generation provider registry.

Usage:
    from src.providers.image_gen import generate_image, TaskType

    image_bytes = generate_image(prompt, task=TaskType.THUMBNAIL)
    image_bytes = generate_image(prompt, task=TaskType.SCENE_IMAGE)

Adding a new provider: add a Provider entry to _PROVIDERS with its
task_scores — no agent code needs to change.
"""
from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
import requests
from loguru import logger


class TaskType(Enum):
    THUMBNAIL = "thumbnail"
    SCENE_IMAGE = "scene_image"


@dataclass
class Provider:
    name: str
    env_key: str          # env var name for the API key; "" = no key needed
    cost_per_image: float  # approximate USD
    max_quality: int       # 1-10 quality score
    supports_landscape: bool
    supports_portrait: bool
    task_scores: dict = field(default_factory=dict)  # TaskType -> float


# Registry ordered best→worst overall; select_provider ranks by task_scores
# for the given task, filtered to providers whose key is present.
_PROVIDERS: list[Provider] = [
    Provider(
        name="dall-e-3",
        env_key="OPENAI_API_KEY",
        cost_per_image=0.06,
        max_quality=9,
        supports_landscape=True,
        supports_portrait=True,
        task_scores={
            TaskType.THUMBNAIL: 1.0,
            TaskType.SCENE_IMAGE: 0.5,  # can generate portrait but DALL-E is costly at volume
        },
    ),
    Provider(
        name="openrouter-gemini-flash-image",
        env_key="OPENROUTER_API_KEY",
        cost_per_image=0.0003,
        max_quality=7,
        supports_landscape=True,
        supports_portrait=True,
        task_scores={
            TaskType.THUMBNAIL: 0.7,
            TaskType.SCENE_IMAGE: 1.0,  # cost-critical volume task, ideal fit
        },
    ),
    Provider(
        name="solid-fallback",
        env_key="",          # no key required
        cost_per_image=0.0,
        max_quality=1,
        supports_landscape=True,
        supports_portrait=True,
        task_scores={
            TaskType.THUMBNAIL: 0.1,
            TaskType.SCENE_IMAGE: 0.1,
        },
    ),
]

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = "google/gemini-2.5-flash-image"


def select_provider(task: TaskType) -> str:
    """
    Return the name of the highest-scoring available provider for *task*.
    A provider is available when its env_key is empty or the env var is set.
    Always returns at least 'solid-fallback'.
    """
    available = [
        p for p in _PROVIDERS
        if not p.env_key or os.environ.get(p.env_key)
    ]
    # _PROVIDERS always contains solid-fallback so available is never empty,
    # but guard anyway.
    if not available:
        return "solid-fallback"
    best = max(available, key=lambda p: p.task_scores.get(task, 0.0))
    logger.debug(
        "image_gen.select_provider: task={} → {} (score={:.2f})",
        task.value, best.name, best.task_scores.get(task, 0.0),
    )
    return best.name


def generate_image(
    prompt: str,
    task: TaskType,
    size_override: Optional[str] = None,
) -> bytes:
    """
    Generate an image for *task* using the best available provider.
    Always returns bytes; falls through to solid-fallback if the selected
    provider fails.
    """
    provider_name = select_provider(task)
    logger.info("image_gen: provider={!r}  task={}", provider_name, task.value)

    if provider_name == "dall-e-3":
        return _generate_dalle3(prompt, task, size_override)
    elif provider_name == "openrouter-gemini-flash-image":
        return _generate_openrouter(prompt, task, size_override)
    else:
        return _generate_fallback(task)


# ---------------------------------------------------------------------------
# Per-provider implementations
# ---------------------------------------------------------------------------

def _generate_dalle3(
    prompt: str, task: TaskType, size_override: Optional[str]
) -> bytes:
    if size_override:
        size = size_override
    elif task == TaskType.THUMBNAIL:
        size = "1792x1024"
    else:
        # Portrait orientation for scene images
        size = "1024x1792"

    api_key = os.environ.get("OPENAI_API_KEY")
    try:
        from openai import OpenAI  # lazy import — only when this provider is used

        client = OpenAI(api_key=api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        url = response.data[0].url
        logger.info("DALL-E 3 image URL: {}", url)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.warning("DALL-E 3 generation failed ({}) — falling back to solid", exc)
        return _generate_fallback(task)


def _generate_openrouter(
    prompt: str, task: TaskType, size_override: Optional[str]
) -> bytes:
    # OpenRouter/Gemini Flash Image does not accept an explicit size parameter —
    # size_override is accepted for API uniformity but ignored here.
    api_key = os.environ.get("OPENROUTER_API_KEY")
    try:
        resp = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data["choices"][0]["message"].get("images") or []
        if not images:
            logger.warning(
                "OpenRouter returned no image for prompt: {!r}", prompt[:80]
            )
            raise ValueError("no image in OpenRouter response")
        data_url = images[0]["image_url"]["url"]
        b64_payload = data_url.split(",", 1)[1] if "," in data_url else data_url
        return base64.b64decode(b64_payload)
    except Exception as exc:
        logger.warning("OpenRouter generation failed ({}) — falling back to solid", exc)
        return _generate_fallback(task)


def _generate_fallback(task: TaskType) -> bytes:
    """Return a solid black image as a last-resort fallback."""
    try:
        from PIL import Image  # lazy import — PIL may not be installed in all envs
    except ImportError:
        logger.warning("PIL not available for solid-fallback; returning empty bytes")
        return b""

    if task == TaskType.THUMBNAIL:
        img = Image.new("RGB", (1280, 720), color=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
    else:
        img = Image.new("RGB", (1080, 1920), color=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    return buf.getvalue()
