"""Per-step config: schema definitions + save/load."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.versions import STEP_FILE_MAP

router = APIRouter(prefix="/steps", tags=["steps"])

VALID_STEPS = ["research", "script", "tts", "characters", "broll",
               "shorts_plan", "shorts_script", "shorts_tts", "shorts_assemble",
               "assemble", "thumbnail"]

STEP_CONFIGS: dict[str, list[dict]] = {
    "research": [
        {"key": "extra_terms", "label": "Extra search terms", "type": "text", "placeholder": "jessica lall bar shooting"},
        {"key": "year_from", "label": "Year from", "type": "number", "placeholder": "1999"},
        {"key": "year_to", "label": "Year to", "type": "number", "placeholder": "2010"},
        {"key": "force_urls", "label": "Force-include URLs (one per line)", "type": "textarea", "placeholder": "https://..."},
    ],
    "script": [
        {"key": "target_duration_min", "label": "Target duration (min)", "type": "number", "default": 35, "min": 20, "max": 50},
        {"key": "tone", "label": "Tone", "type": "select", "options": ["warm documentary", "journalistic", "investigative"], "default": "warm documentary"},
        {"key": "emphasis", "label": "Emphasis on", "type": "text", "placeholder": "victim background, court drama"},
        {"key": "extra_notes", "label": "Notes for writer", "type": "textarea", "placeholder": "Include the 2006 retrial."},
    ],
    "tts": [
        {"key": "voice", "label": "Voice (narrator)", "type": "select",
         "options": ["anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"],
         "default": "anushka"},
        {"key": "speed", "label": "Pace / Speed", "type": "select",
         "options": [
             "0.75|Very slow — dramatic pauses",
             "0.85|Slow — deliberate narration",
             "0.92|Slightly slow (recommended)",
             "1.0|Normal speed",
             "1.15|Slightly fast",
         ],
         "default": "0.92|Slightly slow (recommended)"},
        {"key": "pitch", "label": "Pitch", "type": "number", "default": 0.0, "min": -0.75, "max": 0.75, "step": 0.05},
        {"key": "loudness", "label": "Loudness", "type": "number", "default": 1.0, "min": 0.3, "max": 3.0, "step": 0.1},
    ],
    "broll": [
        {"key": "prefer_character_photos", "label": "Prefer character photos over stock", "type": "boolean", "default": True},
        {"key": "query_overrides", "label": "Section query overrides (JSON)", "type": "textarea", "placeholder": '{"COLD OPEN": "new delhi 1999 bar nightlife"}'},
    ],
    "shorts_plan": [],  # planner decides episode count + angles entirely from research.json, no operator config
    "shorts_script": [],  # one script per planned episode — count comes from shorts_plan.json, not configurable here
    "shorts_tts": [
        {"key": "voice", "label": "Voice", "type": "select",
         "options": ["anushka", "manisha", "vidya", "arya", "abhilash", "karun"],
         "default": "anushka"},
        {"key": "speed", "label": "Speed", "type": "select",
         "options": ["0.85|Slow", "0.92|Slightly slow (recommended)", "1.0|Normal"],
         "default": "0.92|Slightly slow (recommended)"},
        {"key": "pitch", "label": "Pitch", "type": "number", "default": 0.0, "min": -0.75, "max": 0.75, "step": 0.05},
        {"key": "loudness", "label": "Loudness", "type": "number", "default": 1.0, "min": 0.3, "max": 3.0, "step": 0.1},
    ],
    "shorts_assemble": [
        {"key": "add_music", "label": "Background music", "type": "boolean", "default": False},
        {"key": "caption_style", "label": "Caption style", "type": "select",
         "options": ["standard", "bold", "none"], "default": "standard"},
    ],
    "assemble": [
        {"key": "resolution", "label": "Resolution", "type": "select", "options": ["1920x1080", "1280x720"], "default": "1920x1080"},
        {"key": "music_enabled", "label": "Background music", "type": "boolean", "default": False},
        {"key": "crossfade_sec", "label": "Crossfade duration (sec)", "type": "number", "default": 0.5},
    ],
    "thumbnail": [
        {"key": "style", "label": "Style", "type": "select", "options": ["dramatic", "minimal", "investigative"], "default": "dramatic"},
        {"key": "text_overlay", "label": "Text overlay", "type": "text", "placeholder": "जेसिका लाल हत्याकांड"},
    ],
    "characters": [],
}


def _config_path(slug: str, step: str) -> Path:
    p = Path(f"data/cases/{slug}/configs")
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{step}_config.json"

def _load_config(slug: str, step: str) -> dict:
    p = _config_path(slug, step)
    return json.loads(p.read_text()) if p.exists() else {}

def _save_config(slug: str, step: str, config: dict) -> None:
    _config_path(slug, step).write_text(json.dumps(config, indent=2))

def _file_info(path: Path) -> dict:
    if path.exists() and path.is_file():
        return {"exists": True, "size_mb": round(path.stat().st_size / (1024*1024), 3)}
    return {"exists": False, "size_mb": None}


class ConfigSave(BaseModel):
    config: dict


@router.get("/{slug}")
async def list_steps(slug: str):
    """All steps with config schema, current config, and file existence."""
    import asyncio

    def _build():
        result = {}
        base = Path(f"data/cases/{slug}")
        for step in VALID_STEPS:
            file_key = STEP_FILE_MAP.get(step)
            artifact = _file_info(base / file_key) if file_key else {"exists": None}
            result[step] = {
                "step": step,
                "config_schema": STEP_CONFIGS.get(step, []),
                "current_config": _load_config(slug, step),
                "artifact": artifact,
                "is_pivot": step in {"research", "script", "tts"},
            }
        return result

    return await asyncio.to_thread(_build)


@router.get("/{slug}/{step}/config")
async def get_config(slug: str, step: str):
    if step not in VALID_STEPS:
        raise HTTPException(400, f"Invalid step: {step}")
    return {"schema": STEP_CONFIGS.get(step, []), "values": _load_config(slug, step)}


@router.put("/{slug}/{step}/config")
async def save_config(slug: str, step: str, body: ConfigSave):
    if step not in VALID_STEPS:
        raise HTTPException(400, f"Invalid step: {step}")
    import asyncio
    await asyncio.to_thread(_save_config, slug, step, body.config)
    return {"ok": True}
