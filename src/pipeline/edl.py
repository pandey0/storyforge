from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class EDLSegment(BaseModel):
    segment_id: str
    start: float
    end: float
    section: Optional[str] = None  # display/grouping label (e.g. "COLD OPEN")
    source_type: str = "auto"      # auto | broll | character_photo | scene_image
    source_path: Optional[str] = None  # relative to data/cases/{slug}/; None = auto


class EDL(BaseModel):
    track: str            # "longform" | "shorts"
    topic: Optional[str] = None  # shorts only
    segments: list[EDLSegment]


def edl_path(slug: str, track: str, topic: Optional[str] = None) -> Path:
    name = "longform.json" if track == "longform" else f"shorts_{topic}.json"
    return Path(f"data/cases/{slug}/edl/{name}")


def load_edl(slug: str, track: str, topic: Optional[str] = None) -> Optional[EDL]:
    p = edl_path(slug, track, topic)
    if not p.exists():
        return None
    return EDL.model_validate_json(p.read_text(encoding="utf-8"))


def save_edl(slug: str, edl: EDL) -> Path:
    p = edl_path(slug, edl.track, edl.topic)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(edl.model_dump_json(indent=2), encoding="utf-8")
    return p


def get_segment_override(edl: Optional[EDL], segment_id: str) -> Optional[EDLSegment]:
    """Return the override for *segment_id*, or None if absent / source_type=='auto'."""
    if edl is None:
        return None
    seg = next((s for s in edl.segments if s.segment_id == segment_id), None)
    if seg is None or seg.source_type == "auto" or not seg.source_path:
        return None
    return seg


def build_longform_skeleton(slug: str) -> EDL:
    """Skeleton EDL from word_timings.json — every segment defaults to auto."""
    timings_path = Path(f"data/cases/{slug}/audio/word_timings.json")
    segments: list[EDLSegment] = []
    if timings_path.exists():
        raw = json.loads(timings_path.read_text(encoding="utf-8"))
        raw_segments = raw if isinstance(raw, list) else raw.get("segments", raw.get("sections", []))
        for idx, seg in enumerate(raw_segments):
            if not isinstance(seg, dict):
                continue
            start = float(seg.get("start_sec", 0.0))
            end = float(seg.get("end_sec", start))
            segments.append(EDLSegment(
                segment_id=str(idx),
                start=start,
                end=end,
                section=seg.get("section"),
            ))
    return EDL(track="longform", segments=segments)


def build_shorts_skeleton(slug: str, topic: str) -> EDL:
    """Skeleton EDL from an episode's _timings.json — every segment defaults to auto."""
    shorts_dir = Path(f"data/cases/{slug}/shorts")
    segments: list[EDLSegment] = []
    timings_file = None
    if shorts_dir.is_dir():
        for candidate in shorts_dir.glob(f"ep*_{topic}_timings.json"):
            timings_file = candidate
            break
    if timings_file and timings_file.exists():
        raw = json.loads(timings_file.read_text(encoding="utf-8"))
        raw_segments = raw if isinstance(raw, list) else []
        for idx, seg in enumerate(raw_segments):
            if not isinstance(seg, dict):
                continue
            segments.append(EDLSegment(
                segment_id=str(seg.get("segment_index", idx)),
                start=float(seg.get("start_sec", seg.get("start", 0.0))),
                end=float(seg.get("end_sec", seg.get("end", 0.0))),
            ))
    return EDL(track="shorts", topic=topic, segments=segments)
