from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from src.pipeline.edl import (
    EDL,
    build_longform_skeleton,
    build_shorts_skeleton,
    load_edl,
    save_edl,
)

router = APIRouter(prefix="/edl", tags=["edl"])


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
    path = save_edl(slug, edl)
    return {"saved": str(path)}
