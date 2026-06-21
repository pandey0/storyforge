from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.pipeline.edl import (
    EDL,
    build_longform_skeleton,
    build_shorts_skeleton,
    edl_checkpoint_step,
    load_edl,
    save_edl,
)

router = APIRouter(prefix="/edl", tags=["edl"])

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi"}


def _case_id(slug: str) -> str:
    from src.db.models import Case
    from src.db.session import get_session

    with get_session() as session:
        case = session.query(Case).filter_by(slug=slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
        return str(case.id)


@router.get("/{slug}")
async def get_edl(slug: str, track: str, topic: Optional[str] = None):
    if track not in ("longform", "shorts"):
        raise HTTPException(status_code=400, detail="track must be 'longform' or 'shorts'")
    if track == "shorts" and not topic:
        raise HTTPException(status_code=400, detail="topic is required for track='shorts'")

    existing = load_edl(slug, track, topic)
    if existing is not None:
        return existing

    skeleton = build_longform_skeleton(slug) if track == "longform" else build_shorts_skeleton(slug, topic)
    return skeleton


@router.put("/{slug}")
async def put_edl(slug: str, edl: EDL):
    import asyncio

    from src.pipeline.checkpoints import mark_human_edited

    path = save_edl(slug, edl)
    step = edl_checkpoint_step(edl.track, edl.topic)

    def _mark():
        mark_human_edited(_case_id(slug), step, notes="EDL override saved")

    await asyncio.to_thread(_mark)

    return {"saved": str(path)}


@router.post("/{slug}/upload")
async def upload_edl_asset(
    slug: str,
    track: str,
    segment_kind: str,
    topic: Optional[str] = None,
    file: UploadFile = File(...),
):
    """
    Accept a multipart file upload for use as a manual EDL segment override.
    Saves into the same on-disk location the auto-pipeline already uses for
    that asset kind, and returns the relative path (relative to
    data/cases/{slug}/) that the EDL editor should set as source_path.
    """
    if track not in ("longform", "shorts"):
        raise HTTPException(status_code=400, detail="track must be 'longform' or 'shorts'")
    if track == "shorts" and not topic:
        raise HTTPException(status_code=400, detail="topic is required for track='shorts'")
    if segment_kind not in ("broll", "scene_image"):
        raise HTTPException(status_code=400, detail="segment_kind must be 'broll' or 'scene_image'")

    suffix = Path(file.filename or "").suffix.lower()
    if segment_kind == "scene_image" and suffix not in _IMAGE_EXTS:
        raise HTTPException(status_code=422, detail=f"scene_image upload must be one of {sorted(_IMAGE_EXTS)}")
    if segment_kind == "broll" and suffix not in (_IMAGE_EXTS | _VIDEO_EXTS):
        raise HTTPException(status_code=422, detail=f"broll upload must be one of {sorted(_IMAGE_EXTS | _VIDEO_EXTS)}")

    contents = await file.read()

    if segment_kind == "broll":
        # Mirrors broll_agent.py: data/cases/{slug}/broll/
        out_dir = Path(f"data/cases/{slug}/broll")
        rel_dir = "broll"
    else:
        # Mirrors scene_image_agent.py: data/cases/{slug}/scene_images/{topic_or_section}/
        topic_or_section = topic or "longform"
        out_dir = Path(f"data/cases/{slug}/scene_images/{topic_or_section}")
        rel_dir = f"scene_images/{topic_or_section}"

    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"upload_{uuid.uuid4().hex[:8]}{suffix}"
    dest = out_dir / safe_name
    dest.write_bytes(contents)

    return {"source_path": f"{rel_dir}/{safe_name}"}


@router.post("/{slug}/validate")
async def validate_edl_route(slug: str, track: str, topic: Optional[str] = None):
    import asyncio

    from src.agents.edl_validator import validate_edl

    if track not in ("longform", "shorts"):
        raise HTTPException(status_code=400, detail="track must be 'longform' or 'shorts'")
    if track == "shorts" and not topic:
        raise HTTPException(status_code=400, detail="topic is required for track='shorts'")

    def _run():
        case_id = _case_id(slug)
        return validate_edl(case_id, slug, track, topic)

    passed, notes = await asyncio.to_thread(_run)
    return {"passed": passed, "notes": notes}
