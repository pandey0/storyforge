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


def edl_checkpoint_step(track: str, topic: Optional[str] = None) -> str:
    """Checkpoint step name for a given EDL — one lock-in gate PER EPISODE for
    shorts, not one shared per case. A bug in the first cut of this gate keyed
    every EDL (across every shorts episode in a case) off a single literal
    "edl" checkpoint, so locking in episode 1's overrides silently activated
    whatever was saved in every other episode's EDL too. Longform has only one
    EDL per case, so "edl" alone is still correct there.
    """
    return "edl" if track == "longform" else f"edl_shorts_{topic}"


def get_segment_override(edl: Optional[EDL], segment_id: str, slug: str) -> Optional[EDLSegment]:
    """Return the override for *segment_id*, or None if absent / source_type=='auto'.

    Lock-in gate (Phase 21F): an override only takes effect once this EDL's own
    checkpoint (see edl_checkpoint_step — per-episode for shorts) is exactly
    status=="human_approved". Any saved-but-not-yet-approved override (status
    "human_edited" or no checkpoint at all — e.g. a case that has never
    touched the EDL editor) is ignored here and the caller falls back to its
    normal auto-selection logic. *slug* is required to look up the case id and
    check approval; pass the EDL's own case's slug.
    """
    if edl is None:
        return None
    seg = next((s for s in edl.segments if s.segment_id == segment_id), None)
    if seg is None or seg.source_type == "auto" or not seg.source_path:
        return None

    if not _edl_is_approved(slug, edl.track, edl.topic):
        return None

    return seg


def _edl_is_approved(slug: str, track: str, topic: Optional[str] = None) -> bool:
    """Look up the case by slug and check whether THIS EDL's checkpoint (see
    edl_checkpoint_step) is human_approved."""
    from src.db.models import Case
    from src.db.session import get_session
    from src.pipeline.checkpoints import is_approved

    with get_session() as session:
        case = session.query(Case).filter_by(slug=slug).first()
        if case is None:
            return False
        case_id = str(case.id)

    return is_approved(case_id, edl_checkpoint_step(track, topic))


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
