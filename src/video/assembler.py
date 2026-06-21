from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.db.models import Case, Video
from src.db.session import get_session
from src.pipeline.edl import load_edl, get_segment_override
from src.pipeline.state import CaseState
from src.video.palette import (
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VIDEO_BITRATE,
    VIDEO_CODEC,
    AUDIO_CODEC,
    CARD_BG,
    CROSSFADE_DURATION,
)

_MUSIC_PATH = "assets/music/default_track.mp3"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi"}

# Warm grade + vignette as ffmpeg filter chain (applied at final encode)
_GRADE_FILTER = (
    "eq=saturation=0.85:brightness=0.03,"
    "colorbalance=rs=0.04:gs=0.01:bs=-0.04,"
    "vignette=PI/5"
)

# Solid dark card colour in hex for ffmpeg drawbox
_CARD_HEX = "{:02x}{:02x}{:02x}".format(*CARD_BG)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    logger.debug("ffmpeg: {}", " ".join(cmd))
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


class VideoCreator:

    def create(self, state: CaseState) -> CaseState:
        logger.info("VideoCreator.create: slug={}", state.slug)

        timings = self._load_timings(state)
        broll_map = self._load_broll_map(state)
        edl = load_edl(state.slug, "longform")

        if not timings:
            raise RuntimeError("No timing segments — run TTS step first")

        tmp_dir = Path(tempfile.mkdtemp(prefix="vc_"))
        try:
            segment_files = self._build_segments(state.slug, timings, broll_map, tmp_dir, edl=edl)
            logger.info("Built {} segment files", len(segment_files))

            concat_path = str(tmp_dir / "concat_raw.mp4")
            self._concat_segments(segment_files, concat_path)
            logger.info("Concatenated → {}", concat_path)

            output_path = f"data/cases/{state.slug}/output/video_final.mp4"
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            audio_path = state.audio_path
            if audio_path and Path(audio_path).exists():
                self._encode_with_audio(concat_path, audio_path, output_path)
            else:
                logger.warning("No voiceover — encoding video-only")
                self._encode_video_only(concat_path, output_path)

            logger.info("Encoded video → {}", output_path)

            duration = self._probe_duration(output_path)
            logger.info("Total duration: {:.2f}s", duration)

            with get_session() as session:
                self._save_to_db(state, output_path, duration, session)
                case_row = session.query(Case).filter(Case.id == uuid.UUID(state.case_id)).first()
                if case_row:
                    case_row.status = "thumbnail"
                    case_row.updated_at = datetime.now(timezone.utc)

            state.status = "thumbnail"
            state.video_path = output_path
            return state

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Timings / B-roll loading
    # ------------------------------------------------------------------

    def _load_timings(self, state: CaseState) -> list[dict]:
        if not state.timings_path or not Path(state.timings_path).exists():
            logger.warning("timings_path missing: {}", state.timings_path)
            return []

        with open(state.timings_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        segments = raw if isinstance(raw, list) else raw.get("segments", raw.get("sections", []))

        result: list[dict] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            if "duration_est" not in seg:
                seg = dict(seg)
                if "end_sec" in seg and "start_sec" in seg:
                    seg["duration_est"] = max(float(seg["end_sec"]) - float(seg["start_sec"]), 5.0)
                else:
                    seg["duration_est"] = max(seg.get("word_count", 0) / 2.5, 5.0)
            result.append(seg)

        logger.info("Loaded {} segments from {}", len(result), state.timings_path)
        return result

    def _load_broll_map(self, state: CaseState) -> dict[str, str]:
        broll_map: dict[str, str] = {}
        if not state.broll_dir or not Path(state.broll_dir).exists():
            logger.warning("broll_dir missing: {}", state.broll_dir)
            return broll_map

        for file in Path(state.broll_dir).iterdir():
            if not file.is_file():
                continue
            stem = file.stem
            parts = stem.rsplit("_", 1)
            section_key = (parts[0] if len(parts) == 2 and parts[1].isdigit() else stem).replace("_", " ").upper()
            if section_key not in broll_map:
                broll_map[section_key] = str(file)

        logger.info("B-roll map: {} sections → {}", len(broll_map), list(broll_map.keys()))
        return broll_map

    # ------------------------------------------------------------------
    # Per-segment clip building (pure ffmpeg, no Python frame processing)
    # ------------------------------------------------------------------

    def _build_segments(
        self,
        slug: str,
        timings: list[dict],
        broll_map: dict[str, str],
        tmp_dir: Path,
        edl=None,
    ) -> list[str]:
        files: list[str] = []
        for idx, seg in enumerate(timings):
            duration = float(seg.get("duration_est", 30.0))
            section = seg.get("section", "").upper()
            override = get_segment_override(edl, str(idx), slug)
            if override is not None:
                broll_path = f"data/cases/{slug}/{override.source_path}"
            else:
                broll_path = broll_map.get(section)
            out = str(tmp_dir / f"seg_{idx:04d}.mp4")

            if idx == 0 or section == "COLD OPEN":
                self._build_cold_open_ffmpeg(seg, broll_path, out, duration)
            else:
                self._build_segment_ffmpeg(broll_path, out, duration)

            logger.info("Segment {:02d} [{:15s}] → {:.1f}s  broll={}", idx, section or "—", duration, bool(broll_path))
            files.append(out)

        return files

    def _build_segment_ffmpeg(self, broll_path: str | None, out: str, duration: float) -> None:
        ext = Path(broll_path).suffix.lower() if broll_path else ""

        if broll_path and Path(broll_path).exists() and ext in _IMAGE_EXTS:
            # Ken-burns on image via ffmpeg zoompan
            self._ffmpeg_kenburns(broll_path, out, duration)

        elif broll_path and Path(broll_path).exists() and ext in _VIDEO_EXTS:
            # Trim/loop video to exact duration
            self._ffmpeg_trim_loop(broll_path, out, duration)

        else:
            if broll_path:
                logger.warning("B-roll not found: {} — using colour card", broll_path)
            self._ffmpeg_color_card(out, duration)

    def _build_cold_open_ffmpeg(self, segment: dict, broll_path: str | None, out: str, duration: float) -> None:
        tmp = Path(out).parent / f"co_main_{Path(out).name}"
        self._build_segment_ffmpeg(broll_path, str(tmp), duration)

        # 2s black fade-in prefix + main clip
        black = Path(out).parent / f"co_black_{Path(out).name}"
        self._ffmpeg_color_card(str(black), 2.0, color="black")

        # Concat black + main
        concat_list = Path(out).parent / f"co_list_{Path(out).stem}.txt"
        concat_list.write_text(
            f"file '{black.name}'\nfile '{tmp.name}'\n"
        )
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", out,
        ])
        black.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
        concat_list.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # ffmpeg primitive ops
    # ------------------------------------------------------------------

    def _ffmpeg_trim_loop(self, src: str, out: str, duration: float) -> None:
        src_dur = self._probe_duration(src)
        # Build filter: trim to src_dur, loop if needed, scale to target, crossfade not needed here
        loops = int(duration / src_dur) + 2  # enough loops to cover duration
        _run([
            "ffmpeg", "-y",
            "-stream_loop", str(loops), "-i", src,
            "-t", str(duration),
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                  f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(VIDEO_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", out,
        ])

    def _ffmpeg_kenburns(self, src: str, out: str, duration: float) -> None:
        # Ken Burns zoom via ffmpeg zoompan filter
        frames = int(duration * VIDEO_FPS)
        _run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", src,
            "-t", str(duration),
            "-vf", (
                f"zoompan=z='min(zoom+0.0015,1.08)':d={frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", out,
        ])

    def _ffmpeg_color_card(self, out: str, duration: float, color: str = None) -> None:
        c = color or f"0x{_CARD_HEX}"
        _run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={c}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}:d={duration}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", out,
        ])

    # ------------------------------------------------------------------
    # Concatenation
    # ------------------------------------------------------------------

    def _concat_segments(self, files: list[str], out: str) -> None:
        list_path = Path(out).parent / "concat_list.txt"
        list_path.write_text("\n".join(f"file '{f}'" for f in files) + "\n")
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c", "copy", out,
        ])
        list_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Final encode with audio + grade filters
    # ------------------------------------------------------------------

    def _encode_with_audio(self, video_path: str, audio_path: str, out: str) -> None:
        # Normalize voice with loudnorm
        audio_dir = Path(out).parent
        audio_dir.mkdir(parents=True, exist_ok=True)
        norm_audio = str(audio_dir / "mixed_audio.mp3")
        _run([
            "ffmpeg", "-y", "-i", audio_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            norm_audio,
        ])

        # Probe durations and trim/pad to match audio length
        video_dur = self._probe_duration(video_path)
        audio_dur = self._probe_duration(norm_audio)
        trim_dur = min(video_dur, audio_dur)

        _run([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", norm_audio,
            "-t", str(trim_dur),
            "-vf", _GRADE_FILTER,
            "-c:v", VIDEO_CODEC, "-b:v", VIDEO_BITRATE,
            "-c:a", AUDIO_CODEC, "-b:a", "192k",
            "-threads", "4",
            out,
        ])

    def _encode_video_only(self, video_path: str, out: str) -> None:
        _run([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", _GRADE_FILTER,
            "-c:v", VIDEO_CODEC, "-b:v", VIDEO_BITRATE,
            "-an",
            "-threads", "4",
            out,
        ])

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _probe_duration(self, path: str) -> float:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            check=True, capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])

    def _save_to_db(self, state: CaseState, output_path: str, duration: float, session) -> Video:
        file_size_mb: float | None = None
        p = Path(output_path)
        if p.exists():
            file_size_mb = p.stat().st_size / (1024 * 1024)

        video_row = Video(
            case_id=uuid.UUID(state.case_id),
            video_path=output_path,
            audio_path=state.audio_path,
            render_status="done",
            render_ended=datetime.now(timezone.utc),
            duration_sec=duration,
            file_size_mb=file_size_mb,
        )
        session.add(video_row)
        session.flush()
        logger.info("Saved Video row id={} render_status=done", video_row.id)
        return video_row
