"""
Pipeline manifest loader — reads pipeline_defs/*.yaml and returns structured step graphs.

Usage:
    from src.pipeline.manifest import load_manifest, get_stage, list_api_steps

    manifest = load_manifest("longform")   # reads pipeline_defs/longform.yaml
    stages = manifest["stages"]
    runnable = list_api_steps(manifest)    # only steps with api_step != null
"""

import yaml  # PyYAML, already in requirements
from pathlib import Path

_MANIFEST_DIR = Path(__file__).parent.parent.parent / "pipeline_defs"


def load_manifest(name: str) -> dict:
    """Load pipeline_defs/{name}.yaml. Raises FileNotFoundError if missing."""
    path = _MANIFEST_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_api_steps(manifest: dict) -> list[dict]:
    """Return stages where api_step is not null — these are runnable via API."""
    return [s for s in manifest.get("stages", []) if s.get("api_step")]


def get_stage(manifest: dict, stage_id: str) -> dict | None:
    """Find a stage by id."""
    for s in manifest.get("stages", []):
        if s.get("id") == stage_id:
            return s
    return None


def get_track_stages(manifest: dict, track: str) -> list[dict]:
    """Return all stages for a given track ('shared', 'longform', 'shorts')."""
    return [s for s in manifest.get("stages", []) if s.get("track") == track]
