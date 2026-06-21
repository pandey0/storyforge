"""
EDLValidator (Phase 21F)
========================
Advisory-only relevance check for manual EDL segment overrides — never
blocking, mirrors the shape of audio_validator.py / character_validator.py:
compute pass/fail + reasons, record via the generic checkpoint primitive
(src/pipeline/checkpoints.py mark_ai_validated), and let the human decide
whether to lock the overrides in (POST /api/checkpoints/{slug}/edl/approve)
regardless of the verdict.

Checks per non-"auto" segment:
  - scene_image / image file overrides: Gemini Vision describes the image in
    one line, then a second small text-only Gemini call judges whether that
    description plausibly matches the segment's narration text. Mismatches
    are flagged but never removed/blocked.
  - broll (video) overrides: too expensive/unreliable to validate video frame
    content cheaply — only confirm the file exists and is a valid video via
    ffprobe (same subprocess pattern as audio_validator.py's _probe_duration).
  - character_photo overrides: same file-exists check as broll (no per-frame
    relevance judgement attempted — these are vetted at the characters step).

Segments with source_type == "auto" are skipped entirely (nothing to check).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from loguru import logger

from src.pipeline.checkpoints import mark_ai_validated
from src.pipeline.edl import EDLSegment, edl_checkpoint_step, load_edl

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_edl(case_id: str, slug: str, track: str, topic: str | None = None) -> tuple[bool, str]:
    """
    Run the advisory relevance check across every overridden segment in the
    EDL for (slug, track, topic). Returns (passed, notes) and records the
    result against the "edl" checkpoint via mark_ai_validated. Never blocks —
    the lock-in gate (mark_human_approved) is a fully separate, explicit
    human action regardless of this verdict.
    """
    step = edl_checkpoint_step(track, topic)
    edl = load_edl(slug, track, topic)
    if edl is None:
        passed, notes = True, "no EDL saved yet — nothing to validate"
        mark_ai_validated(case_id, step, passed, notes=notes)
        return passed, notes

    reasons: list[str] = []
    case_dir = Path(f"data/cases/{slug}")

    for seg in edl.segments:
        if seg.source_type == "auto" or not seg.source_path:
            continue

        abs_path = case_dir / seg.source_path
        reason = _check_segment(seg, abs_path)
        if reason:
            reasons.append(f"segment {seg.segment_id}: {reason}")

    passed = not reasons
    notes = "; ".join(reasons)

    mark_ai_validated(case_id, step, passed, notes=notes or None)
    logger.info(
        "EDL validation [{}/{}{}]: passed={} notes={}",
        slug, track, f"/{topic}" if topic else "", passed, notes or "(none)",
    )
    return passed, notes


def _check_segment(seg: EDLSegment, abs_path: Path) -> str | None:
    if not abs_path.exists():
        return f"source_path does not exist on disk: {abs_path}"

    suffix = abs_path.suffix.lower()
    is_image = seg.source_type == "scene_image" or suffix in _IMAGE_EXTS

    if is_image:
        return _check_image_relevance(seg, abs_path)

    # broll (video) and character_photo (already vetted at characters step):
    # just confirm the file is a valid, probeable video — no content judgement.
    if seg.source_type == "broll":
        return _check_video_valid(abs_path)

    return None


# ---------------------------------------------------------------------------
# Image relevance (Gemini Vision describe + text-only relevance judgement)
# ---------------------------------------------------------------------------


def _check_image_relevance(seg: EDLSegment, abs_path: Path) -> str | None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set — skipping image relevance check for segment {}", seg.segment_id)
        return None

    narration = (seg.section or "").strip()
    if not narration:
        # Nothing to compare the image against — skip rather than false-flag.
        return None

    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        image = Image.open(abs_path)
        description_response = model.generate_content(
            [
                "Describe this image in one short sentence, focused on what scene/subject it depicts.",
                image,
            ],
            generation_config=genai.types.GenerationConfig(temperature=0.0, max_output_tokens=300),
        )
        description = (description_response.text or "").strip()
        if not description:
            return "could not generate an image description"

        judge_prompt = (
            "An editor manually picked an image for a video segment. Given the image's "
            "description and the segment's narration/section label, does the image plausibly "
            "fit the narration? Answer ONLY YES or NO, optionally followed by a colon and a "
            "short reason if NO.\n\n"
            f"IMAGE DESCRIPTION: {description}\n"
            f"SEGMENT NARRATION/SECTION: {narration}"
        )
        judge_response = model.generate_content(
            judge_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0, max_output_tokens=300),
        )
        verdict = (judge_response.text or "").strip()
        if verdict.upper().startswith("NO"):
            return f"image may not match narration — {verdict}" if verdict else "image may not match narration"
        return None

    except Exception as exc:
        logger.warning("Image relevance check failed for segment {}: {}", seg.segment_id, exc)
        return None


# ---------------------------------------------------------------------------
# Video file sanity (ffprobe) — same pattern as audio_validator.py
# ---------------------------------------------------------------------------


def _check_video_valid(abs_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(abs_path)],
            check=True, capture_output=True, text=True,
        )
        probe_data = json.loads(result.stdout)
        streams = probe_data.get("streams", [])
        if not any(s.get("codec_type") == "video" for s in streams):
            return f"file has no video stream: {abs_path}"
        return None
    except Exception as exc:
        return f"ffprobe failed on {abs_path}: {exc}"
