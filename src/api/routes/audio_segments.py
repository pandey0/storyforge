"""
Audio segment replacement — splice a replacement narration clip into an
already-generated voiceover.mp3 (longform) or episode mp3 (shorts), keyed by
word_timings.json segment_idx.

Distinct concern from src/api/routes/audio.py (which does whole-file
tempo/pitch/volume post-processing) and from src/pipeline/edl.py (which
selects VISUAL b-roll/character-photo/scene-image sources — a different
asset class entirely). This module only swaps narration audio for one
segment and re-syncs downstream segment timings.

Route prefix: /audio-segments — distinct from /audio (audio.py) to avoid any
path collision.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.pipeline.checkpoints import mark_ai_validated, mark_human_edited

router = APIRouter(prefix="/audio-segments", tags=["audio-segments"])


def _case_id(slug: str) -> str:
    from src.db.models import Case
    from src.db.session import get_session

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
        return str(case.id)


def _resolve_paths(slug: str, track: str, topic: Optional[str]) -> tuple[Path, Path]:
    """Return (mp3_path, timings_path) for the given track/topic."""
    if track == "longform":
        mp3_path = Path(f"data/cases/{slug}/audio/voiceover.mp3")
        timings_path = Path(f"data/cases/{slug}/audio/word_timings.json")
        return mp3_path, timings_path

    if track == "shorts":
        if not topic:
            raise HTTPException(status_code=400, detail="topic is required for track='shorts'")
        shorts_dir = Path(f"data/cases/{slug}/shorts")
        mp3_matches = sorted(shorts_dir.glob(f"ep*_{topic}.mp3")) if shorts_dir.is_dir() else []
        if not mp3_matches:
            raise HTTPException(status_code=404, detail=f"No episode mp3 found for {slug}/{topic}")
        mp3_path = mp3_matches[0]
        timings_path = mp3_path.with_name(mp3_path.stem + "_timings.json")
        return mp3_path, timings_path

    raise HTTPException(status_code=400, detail=f"Unknown track: {track!r}")


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


@router.post("/{slug}/{segment_idx}/replace")
async def replace_audio_segment(
    slug: str,
    segment_idx: int,
    track: str = "longform",
    topic: Optional[str] = None,
    file: UploadFile = File(...),
):
    """
    Splice a replacement audio clip into the existing voiceover at the
    segment boundaries given by word_timings.json[segment_idx].

    Steps:
      1. Locate mp3 + timings JSON for the track/topic.
      2. Find segment by segment_idx; read its start_sec/end_sec.
      3. ffmpeg: extract [0, start_sec) as part A, [end_sec, EOF) as part B.
      4. Convert uploaded clip to matching wav format.
      5. Concat A + replacement + B → new mp3, overwrite original.
      6. Recompute new segment duration; shift all subsequent segments'
         start_sec/end_sec by the delta; write timings JSON back.
      7. mark_human_edited + validate_audio + mark_ai_validated.
    """
    if track not in ("longform", "shorts"):
        raise HTTPException(status_code=400, detail="track must be 'longform' or 'shorts'")

    case_id = _case_id(slug)
    mp3_path, timings_path = _resolve_paths(slug, track, topic)

    if not mp3_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {mp3_path}")
    if not timings_path.exists():
        raise HTTPException(status_code=404, detail=f"Timings file not found: {timings_path}")

    try:
        timings: list[dict] = json.loads(timings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read timings JSON: {exc}")

    segment = next((s for s in timings if s.get("segment_idx") == segment_idx), None)
    if segment is None:
        raise HTTPException(status_code=404, detail=f"Segment {segment_idx} not found in timings")

    old_start = float(segment["start_sec"])
    old_end = float(segment["end_sec"])
    old_duration = old_end - old_start

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    step = "tts" if track == "longform" else "shorts_tts"

    tmp_dir = Path(tempfile.mkdtemp(prefix="audio_segment_replace_"))
    try:
        upload_suffix = Path(file.filename or "clip.wav").suffix or ".wav"
        raw_upload_path = tmp_dir / f"upload{upload_suffix}"
        raw_upload_path.write_bytes(contents)

        # Convert uploaded clip to match the project's mono 22050Hz convention
        # (same format tts_agent.py's _merge_wav_to_mp3 produces).
        replacement_wav = tmp_dir / "replacement.wav"
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(raw_upload_path),
            "-ar", "22050", "-ac", "1",
            str(replacement_wav),
        ])

        part_a = tmp_dir / "part_a.wav"
        part_b = tmp_dir / "part_b.wav"

        if old_start > 0:
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(mp3_path),
                "-t", str(old_start),
                "-ar", "22050", "-ac", "1",
                str(part_a),
            ])
        else:
            part_a = None

        full_duration = _probe_duration(str(mp3_path))
        if old_end < full_duration:
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(mp3_path),
                "-ss", str(old_end),
                "-ar", "22050", "-ac", "1",
                str(part_b),
            ])
        else:
            part_b = None

        # Concat A + replacement + B via concat demuxer (same pattern as
        # tts_agent.py's _merge_wav_to_mp3).
        pieces = [p for p in (part_a, replacement_wav, part_b) if p is not None]
        concat_wav = tmp_dir / "concat.wav"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as flist:
            flist_path = flist.name
            for p in pieces:
                flist.write(f"file '{p.resolve()}'\n")
        try:
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", flist_path,
                "-c", "copy",
                "-ar", "22050", "-ac", "1",
                str(concat_wav),
            ])
        finally:
            Path(flist_path).unlink(missing_ok=True)

        # Re-encode to mp3, overwrite original.
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(concat_wav),
            "-codec:a", "libmp3lame",
            "-b:a", "128k",
            "-ar", "22050",
            "-ac", "1",
            "-write_xing", "1",
            str(mp3_path),
        ])

        new_duration_total = _probe_duration(str(mp3_path))
        replacement_duration = _probe_duration(str(replacement_wav))
        delta = replacement_duration - old_duration

        # Update the replaced segment + shift all subsequent ones.
        for s in timings:
            if s.get("segment_idx") == segment_idx:
                s["start_sec"] = round(old_start, 3)
                s["end_sec"] = round(old_start + replacement_duration, 3)
            elif float(s.get("start_sec", 0.0)) > old_start:
                s["start_sec"] = round(float(s["start_sec"]) + delta, 3)
                s["end_sec"] = round(float(s["end_sec"]) + delta, 3)

        timings_path.write_text(json.dumps(timings, indent=2, ensure_ascii=False), encoding="utf-8")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    mark_human_edited(case_id, step, notes=f"segment {segment_idx} replaced")

    from src.agents.audio_validator import validate_audio
    passed, notes = validate_audio(case_id, slug, track=track, topic=topic)

    return {
        "replaced": True,
        "segment_idx": segment_idx,
        "old_duration": round(old_duration, 3),
        "new_duration": round(replacement_duration, 3),
        "delta_sec": round(delta, 3),
        "total_duration": round(new_duration_total, 3),
        "validation": {"passed": passed, "notes": notes},
    }


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg command failed: {' '.join(cmd)}\n{result.stderr[-1000:]}",
        )
