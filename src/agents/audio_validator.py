"""
AudioValidator
==============
Purely deterministic post-generation sanity checks for TTS output — no LLM
call. Runs after TTSAgent (longform) or the per-episode shorts TTS loop
completes, to catch obviously broken audio (truncated synthesis, dead air,
clipping) before a human reviews it.

Checks:
  1. Duration vs. word-count estimate (longform only — shorts has no fixed
     script-duration relationship since episodes are short/variable; shorts
     just gets a sanity range).
  2. Silence gaps > 5s (a real production gap, distinct from intentional
     [PAUSE Xs] markers which are normally 1-3s).
  3. Mean loudness within a sane voice-over band.

This module only computes pass/fail + reasons and records the result via the
existing generic checkpoint primitive (src/pipeline/checkpoints.py). It does
not retry or regenerate audio — that stays a human/AI-judgement call via the
checkpoint UI.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from loguru import logger

from src.pipeline.checkpoints import mark_ai_validated

# Longform sanity bounds
_LONGFORM_DURATION_TOLERANCE = 0.40  # flag if actual differs from estimate by >40%

# Shorts has no fixed WPM relationship — just a sane absolute range (seconds)
_SHORTS_MIN_DURATION = 30.0
_SHORTS_MAX_DURATION = 150.0

# Silence: flag any gap longer than this many seconds (longer than a normal
# [PAUSE Xs] marker, which is usually 1-3s) — likely a real production gap.
_MAX_SILENCE_GAP_SEC = 5.0
_SILENCE_NOISE_DB = "-30dB"
_SILENCE_MIN_DURATION = 2.0

# Loudness band (dB) — outside this, audio is too quiet or clipping-risk loud.
_MIN_MEAN_VOLUME_DB = -35.0
_MAX_MEAN_VOLUME_DB = -5.0

_SILENCE_DURATION_RE = re.compile(r"silence_duration:\s*([\d.]+)")
_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?[\d.]+)\s*dB")
_DEFAULT_WPM = 130  # longform fallback if profile lookup fails


def validate_audio(
    case_id: str,
    slug: str,
    track: str = "longform",
    topic: str | None = None,
) -> tuple[bool, str]:
    """
    Run deterministic checks on the generated voiceover and record the
    result via mark_ai_validated against the matching checkpoint step
    ("tts" for longform; "shorts_tts_{topic}" for shorts — one checkpoint PER
    EPISODE, not shared across every episode in the case, same fix as EDL's
    edl_checkpoint_step).

    Returns (passed, notes) — notes is a comma-joined list of failure
    reasons, or "" if all checks passed.
    """
    step = "tts" if track == "longform" else f"shorts_tts_{topic}"

    try:
        mp3_path = _resolve_mp3_path(slug, track, topic)
    except FileNotFoundError as exc:
        passed, notes = False, str(exc)
        mark_ai_validated(case_id, step, passed, notes=notes)
        return passed, notes

    reasons: list[str] = []

    try:
        duration = _probe_duration(str(mp3_path))
    except Exception as exc:
        reasons.append(f"ffprobe failed: {exc}")
        duration = None

    if duration is not None:
        duration_reason = _check_duration(slug, track, topic, duration)
        if duration_reason:
            reasons.append(duration_reason)

    try:
        silence_reason = _check_silence(str(mp3_path))
        if silence_reason:
            reasons.append(silence_reason)
    except Exception as exc:
        reasons.append(f"silence check failed: {exc}")

    try:
        loudness_reason = _check_loudness(str(mp3_path))
        if loudness_reason:
            reasons.append(loudness_reason)
    except Exception as exc:
        reasons.append(f"loudness check failed: {exc}")

    passed = not reasons
    notes = ", ".join(reasons)

    mark_ai_validated(case_id, step, passed, notes=notes or None)
    logger.info(
        "Audio validation [{}/{}]: passed={} notes={}",
        slug, track, passed, notes or "(none)",
    )
    return passed, notes


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_mp3_path(slug: str, track: str, topic: str | None) -> Path:
    if track == "longform":
        path = Path(f"data/cases/{slug}/audio/voiceover.mp3")
        if not path.exists():
            raise FileNotFoundError(f"voiceover.mp3 not found for slug={slug!r}")
        return path

    if track == "shorts":
        if not topic:
            raise FileNotFoundError("topic is required for track='shorts'")
        shorts_dir = Path(f"data/cases/{slug}/shorts")
        matches = sorted(shorts_dir.glob(f"ep*_{topic}.mp3")) if shorts_dir.is_dir() else []
        if not matches:
            raise FileNotFoundError(f"No episode mp3 found for {slug}/{topic}")
        return matches[0]

    raise FileNotFoundError(f"Unknown track: {track!r}")


# ---------------------------------------------------------------------------
# ffprobe / ffmpeg helpers — same invocation pattern as tts_agent.py /
# shorts_assembler_agent.py's _probe_duration
# ---------------------------------------------------------------------------


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        check=True, capture_output=True, text=True,
    )
    probe_data = json.loads(result.stdout)
    return float(probe_data["format"]["duration"])


def _check_duration(slug: str, track: str, topic: str | None, actual_duration: float) -> str | None:
    if track == "shorts":
        if actual_duration < _SHORTS_MIN_DURATION or actual_duration > _SHORTS_MAX_DURATION:
            return (
                f"shorts duration {actual_duration:.1f}s outside sane range "
                f"[{_SHORTS_MIN_DURATION:.0f}s, {_SHORTS_MAX_DURATION:.0f}s]"
            )
        return None

    # longform — compare against word-count / WPM estimate
    word_count = _script_word_count(slug)
    if word_count is None:
        return None  # can't estimate — skip this check rather than false-flag

    wpm = _DEFAULT_WPM
    try:
        from src.db.channel_profile import get_profile_for_case
        profile = get_profile_for_case(slug)
        wpm = profile.words_per_minute or _DEFAULT_WPM
    except Exception as exc:
        logger.warning("Could not load profile WPM for {} — using default {}: {}", slug, _DEFAULT_WPM, exc)

    expected = (word_count / wpm) * 60.0
    if expected <= 0:
        return None

    delta_ratio = abs(actual_duration - expected) / expected
    if delta_ratio > _LONGFORM_DURATION_TOLERANCE:
        return (
            f"duration {actual_duration:.1f}s differs from word-count estimate "
            f"{expected:.1f}s by {delta_ratio * 100:.0f}% (>{_LONGFORM_DURATION_TOLERANCE * 100:.0f}% tolerance)"
        )
    return None


def _script_word_count(slug: str) -> int | None:
    manual = Path(f"data/cases/{slug}/script_manual.md")
    draft = Path(f"data/cases/{slug}/script_draft.md")
    path = manual if manual.exists() else draft
    if not path.exists():
        return None
    try:
        return len(path.read_text(encoding="utf-8").split())
    except OSError:
        return None


def _check_silence(path: str) -> str | None:
    result = subprocess.run(
        [
            "ffmpeg", "-i", path,
            "-af", f"silencedetect=noise={_SILENCE_NOISE_DB}:d={_SILENCE_MIN_DURATION}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    durations = [float(m) for m in _SILENCE_DURATION_RE.findall(result.stderr)]
    long_gaps = [d for d in durations if d > _MAX_SILENCE_GAP_SEC]
    if long_gaps:
        worst = max(long_gaps)
        return f"silence gap of {worst:.1f}s exceeds {_MAX_SILENCE_GAP_SEC:.0f}s threshold ({len(long_gaps)} gap(s))"
    return None


def _check_loudness(path: str) -> str | None:
    result = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = _MEAN_VOLUME_RE.search(result.stderr)
    if not m:
        return None  # couldn't parse — don't false-flag
    mean_db = float(m.group(1))
    if mean_db < _MIN_MEAN_VOLUME_DB:
        return f"mean volume {mean_db:.1f}dB too quiet (<{_MIN_MEAN_VOLUME_DB:.0f}dB)"
    if mean_db > _MAX_MEAN_VOLUME_DB:
        return f"mean volume {mean_db:.1f}dB risks clipping (>{_MAX_MEAN_VOLUME_DB:.0f}dB)"
    return None
