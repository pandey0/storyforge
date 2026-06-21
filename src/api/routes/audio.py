"""Audio post-processing: tempo, pitch, volume adjustments via ffmpeg."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/audio", tags=["audio"])


class ProcessBody(BaseModel):
    tempo: float = 1.0      # 0.5–2.0, rubberband pitch-independent
    pitch: float = 1.0      # 0.5–2.0, semitone multiplier (rubberband)
    volume: float = 1.0     # 0.5–2.0, linear gain
    preview_only: bool = False  # if True, process first 30s only into voiceover_preview.mp3


@router.post("/{slug}/process")
async def process_audio(slug: str, body: ProcessBody):
    audio_dir = Path(f"data/cases/{slug}/audio")
    src = audio_dir / "voiceover.mp3"
    original = audio_dir / "voiceover_original.mp3"

    if not src.exists():
        raise HTTPException(404, "No voiceover.mp3 found — run TTS first")

    # Clamp values to safe ranges
    tempo  = max(0.5, min(2.0, body.tempo))
    pitch  = max(0.5, min(2.0, body.pitch))
    volume = max(0.1, min(4.0, body.volume))

    def _run():
        # Keep original backup (only on first process call)
        if not original.exists():
            shutil.copy2(str(src), str(original))

        input_path = str(original)  # always process from original
        out_name = "voiceover_preview.mp3" if body.preview_only else "voiceover.mp3"
        output_path = str(audio_dir / out_name)

        # Build rubberband filter: handles tempo + pitch independently
        # rubberband tempo= pitch= (pitch is in semitones ratio, 1.0 = unchanged)
        rb = f"rubberband=tempo={tempo:.3f}:pitch={pitch:.3f}"
        vol = f"volume={volume:.3f}"
        filter_chain = f"{rb},{vol}"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
        ]
        if body.preview_only:
            cmd += ["-t", "30"]

        cmd += [
            "-filter:a", filter_chain,
            "-codec:a", "libmp3lame",
            "-b:a", "128k",
            "-ar", "22050",
            "-ac", "1",
            "-write_xing", "1",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")

        # Return duration of processed file
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", output_path],
            capture_output=True, text=True
        )
        import json
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        return {
            "ok": True,
            "output": out_name,
            "duration_sec": round(duration, 1),
            "duration_min": round(duration / 60, 2),
            "size_mb": round(size_mb, 2),
            "settings": {"tempo": tempo, "pitch": pitch, "volume": volume},
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{slug}/reset")
async def reset_audio(slug: str):
    """Restore original voiceover (before any post-processing)."""
    audio_dir = Path(f"data/cases/{slug}/audio")
    original = audio_dir / "voiceover_original.mp3"
    current  = audio_dir / "voiceover.mp3"

    if not original.exists():
        raise HTTPException(404, "No original backup found")

    def _reset():
        shutil.copy2(str(original), str(current))
        import json, subprocess as sp
        probe = sp.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(current)],
            capture_output=True, text=True
        )
        dur = float(json.loads(probe.stdout)["format"]["duration"])
        return {"ok": True, "duration_min": round(dur / 60, 2)}

    return await asyncio.to_thread(_reset)


@router.get("/{slug}/info")
async def audio_info(slug: str):
    """Return duration + whether original backup exists."""
    audio_dir = Path(f"data/cases/{slug}/audio")
    src = audio_dir / "voiceover.mp3"
    original = audio_dir / "voiceover_original.mp3"

    if not src.exists():
        return {"exists": False}

    def _info():
        import json, subprocess as sp
        probe = sp.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(src)],
            capture_output=True, text=True
        )
        dur = float(json.loads(probe.stdout)["format"]["duration"])
        size_mb = src.stat().st_size / (1024 * 1024)
        return {
            "exists": True,
            "duration_sec": round(dur, 1),
            "duration_min": round(dur / 60, 2),
            "size_mb": round(size_mb, 2),
            "has_original": original.exists(),
            "preview_exists": (audio_dir / "voiceover_preview.mp3").exists(),
        }

    return await asyncio.to_thread(_info)
