from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests
from loguru import logger

from src.db.models import Case, Script, Video
from src.db.session import get_session
from src.pipeline.state import CaseState

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_CHUNK_SIZE = 400  # chars per request (Bulbul v2 limit is 500, keep headroom)

_PAUSE_RE = re.compile(r"\[PAUSE\s*(\d+(?:\.\d+)?)\s*s\]", re.IGNORECASE)

# All TTS control markers in one pattern: PAUSE (group 1=seconds) or PACE (group 2=tag)
_MARKER_RE = re.compile(
    r"\[PAUSE\s*(\d+(?:\.\d+)?)\s*s\]|\[(SLOW|FAST|DRAMATIC|NORMAL)\]",
    re.IGNORECASE,
)
# None means "use self.speed" (the global pace set via UI / config)
_PACE_MAP: dict[str, float | None] = {
    "dramatic": 0.65,   # very slow — major reveals
    "slow":     0.75,   # emotional / reflective passages
    "normal":   None,   # reset to base speed
    "fast":     1.10,   # action sequences, rapid events
}


class TTSAgent:
    # Valid Sarvam Bulbul v2 speakers for hi-IN (verified 2026-06)
    VALID_SPEAKERS = {"anushka", "abhilash", "manisha", "vidya", "arya", "karun", "hitesh"}

    def __init__(
        self,
        speaker: str | None = None,
        speed: float = 0.92,
        pitch: float = 0.0,
        loudness: float = 1.0,
        target_language_code: str = "hi-IN",
    ) -> None:
        self.api_key = os.environ.get("SARVAM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY not set in environment")
        raw_speaker = speaker or os.environ.get("SARVAM_SPEAKER", "anushka")
        self.speaker = raw_speaker if raw_speaker in self.VALID_SPEAKERS else "anushka"
        self.speed = max(0.5, min(2.0, speed))
        # Sarvam Bulbul v2 valid ranges: pitch -0.75..0.75, loudness 0.3..3.0
        self.pitch = max(-0.75, min(0.75, pitch))
        self.loudness = max(0.3, min(3.0, loudness))
        self.target_language_code = target_language_code or "hi-IN"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, state: CaseState) -> CaseState:
        t_start = time.time()

        script_text = self._load_script(state)
        # Clean everything EXCEPT TTS control markers — we handle them in _split_into_items
        pre_cleaned = self._clean_for_tts(script_text, keep_pauses=True)
        items = self._split_into_items(pre_cleaned)

        audio_dir = Path(f"data/cases/{state.slug}/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(audio_dir / "voiceover.mp3")

        wav_paths: list[str] = []
        speech_idx = 0
        pause_idx = 0

        for item in items:
            if item["type"] == "pause":
                duration = item["duration"]
                wav_path = str(audio_dir / f"pause_{pause_idx:04d}.wav")
                self._generate_silence_wav(duration, wav_path)
                wav_paths.append(wav_path)
                logger.info(f"Silence gap: {duration}s → {wav_path}")
                pause_idx += 1
            else:
                item_pace = item.get("pace")  # None → fall back to self.speed
                actual_pace = item_pace if item_pace is not None else self.speed
                chunks = self._split_into_chunks(item["content"], max_chars=SARVAM_CHUNK_SIZE)
                for chunk in chunks:
                    logger.info(f"TTS speech chunk {speech_idx}: {len(chunk)} chars, pace={actual_pace:.2f}")
                    wav_path = str(audio_dir / f"chunk_{speech_idx:04d}.wav")
                    self._synthesize_chunk(chunk, wav_path, pace=actual_pace)
                    wav_paths.append(wav_path)
                    speech_idx += 1
                    time.sleep(0.3)

        self._merge_wav_to_mp3(wav_paths, output_path)
        self._cleanup_chunks(wav_paths)

        total = speech_idx + pause_idx
        timings = self._extract_word_timings(output_path, script_text)
        timings_path = self._save_timings(timings, str(audio_dir / "word_timings.json"))

        with get_session() as session:
            case_row = session.query(Case).filter(Case.slug == state.slug).one()
            script_row = (
                session.query(Script)
                .filter(Script.case_id == case_row.id)
                .order_by(Script.created_at.desc())
                .first()
            )
            video_row = Video(
                id=uuid.uuid4(),
                case_id=case_row.id,
                script_id=script_row.id if script_row else None,
                audio_path=output_path,
                render_status="pending",
            )
            session.add(video_row)
            case_row.status = "broll"

        duration = time.time() - t_start
        logger.info(f"TTS complete: {total} chunks, {duration:.1f}s elapsed")

        state.audio_path = output_path
        state.timings_path = timings_path
        state.status = "broll"
        return state

    # ------------------------------------------------------------------
    # Script loading
    # ------------------------------------------------------------------

    def _load_script(self, state: CaseState) -> str:
        # Manual script written via terminal Claude takes highest priority
        manual = Path(f"data/cases/{state.slug}/script_manual.md")
        if manual.exists():
            logger.info(f"Using manual script: {manual}")
            return manual.read_text(encoding="utf-8")

        path = state.script_path or state.draft_script_path
        if not path:
            raise ValueError(f"No script path on state for slug={state.slug!r}")
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    # ------------------------------------------------------------------
    # Text cleaning
    # ------------------------------------------------------------------

    def _clean_for_tts(self, script: str, keep_pauses: bool = False) -> str:
        # Remove markdown section headers
        text = re.sub(r"^##\s*\[.*?\]\s*$", "", script, flags=re.MULTILINE)

        # Remove [SOURCE: ...] citations
        text = re.sub(r"\[SOURCE:[^\]]*\]", "", text)

        if not keep_pauses:
            # Strip pause markers when we don't need them
            text = _PAUSE_RE.sub("", text)

        # Strip bracket constructs, keeping TTS control markers when requested
        if keep_pauses:
            # Keep [PAUSE Xs], [SLOW], [FAST], [DRAMATIC], [NORMAL]; strip everything else
            text = re.sub(
                r"\[(?!PAUSE\b)(?!SLOW\b)(?!FAST\b)(?!DRAMATIC\b)(?!NORMAL\b)[^\]]*\]",
                "",
                text,
                flags=re.IGNORECASE,
            )
        else:
            text = re.sub(r"\[[^\]]*\]", "", text)

        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        text = "\n".join(line.strip() for line in text.splitlines())

        return text.strip()

    # ------------------------------------------------------------------
    # Marker splitting — speech/silence items with per-segment pace
    # ------------------------------------------------------------------

    def _split_into_items(self, text: str) -> list[dict]:
        """Scan for [PAUSE Xs] and [SLOW/FAST/DRAMATIC/NORMAL] markers.

        Returns list of:
          {"type": "speech", "content": str, "pace": float|None}
          {"type": "pause",  "duration": float}

        pace=None means use self.speed (the global base configured via UI).
        Pace markers are stateful: [SLOW] affects all following speech until
        the next marker or end of text.
        """
        items: list[dict] = []
        current_pace: float | None = None  # None → self.speed
        last = 0

        for m in _MARKER_RE.finditer(text):
            speech = text[last : m.start()].strip()
            if speech:
                items.append({"type": "speech", "content": speech, "pace": current_pace})

            if m.group(1) is not None:
                # [PAUSE Xs]
                items.append({"type": "pause", "duration": float(m.group(1))})
            else:
                # Pace switch — update state, no audio item emitted
                current_pace = _PACE_MAP.get(m.group(2).lower())

            last = m.end()

        trailing = text[last:].strip()
        if trailing:
            items.append({"type": "speech", "content": trailing, "pace": current_pace})

        return items

    def _generate_silence_wav(self, duration_sec: float, output_path: str) -> str:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=22050:cl=mono",
                "-t", str(duration_sec),
                "-ar", "22050",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        return output_path

    # ------------------------------------------------------------------
    # Chunking — at paragraph boundaries, max 450 chars
    # ------------------------------------------------------------------

    def _split_into_chunks(self, text: str, max_chars: int = SARVAM_CHUNK_SIZE) -> list[str]:
        paragraphs = re.split(r"\n\n+", text)
        chunks: list[str] = []
        current = ""

        def _flush_para(para: str) -> None:
            """Append para to chunks, splitting at sentence boundary if oversized."""
            nonlocal current
            if len(para) <= max_chars:
                if not current:
                    current = para
                elif len(current) + 2 + len(para) <= max_chars:
                    current = current + "\n\n" + para
                else:
                    chunks.append(current)
                    current = para
            else:
                # Para exceeds max — flush current first, then split para
                if current:
                    chunks.append(current)
                    current = ""
                sentences = re.split(r"(?<=[।.!?])\s+", para)
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if not current:
                        current = sent
                    elif len(current) + 1 + len(sent) <= max_chars:
                        current = current + " " + sent
                    else:
                        chunks.append(current)
                        current = sent

        for para in paragraphs:
            para = para.strip()
            if para:
                _flush_para(para)

        if current:
            chunks.append(current)

        return chunks

    # ------------------------------------------------------------------
    # Sarvam Bulbul synthesis
    # ------------------------------------------------------------------

    def _synthesize_chunk(self, text: str, output_wav_path: str, pace: float | None = None) -> str:
        payload = {
            "inputs": [text],
            "target_language_code": self.target_language_code,
            "speaker": self.speaker,
            "model": "bulbul:v2",
            "enable_preprocessing": True,
            "speech_sample_rate": 22050,
            "pace": pace if pace is not None else self.speed,
            "pitch": self.pitch,
            "loudness": self.loudness,
        }
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            resp = requests.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                audio_b64 = data["audios"][0]
                audio_bytes = base64.b64decode(audio_b64)
                with open(output_wav_path, "wb") as fh:
                    fh.write(audio_bytes)
                return output_wav_path
            if resp.status_code == 429:
                logger.warning(f"Sarvam rate-limited — waiting 30s (attempt {attempt + 1}/3)")
                time.sleep(30)
                continue
            logger.error(f"Sarvam {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()

        raise RuntimeError(f"Sarvam TTS failed after 3 attempts (last status {resp.status_code})")

    # ------------------------------------------------------------------
    # Audio merging
    # ------------------------------------------------------------------

    def _merge_wav_to_mp3(self, wav_paths: list[str], output_mp3: str) -> str:
        # Stage 1: concat all WAVs into one intermediate WAV
        # (ffmpeg concat demuxer knows exact sample count → correct duration)
        concat_wav = output_mp3.replace(".mp3", "_concat_tmp.wav")

        if len(wav_paths) == 1:
            concat_wav = wav_paths[0]
        else:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as flist:
                flist_path = flist.name
                for wp in wav_paths:
                    flist.write(f"file '{os.path.abspath(wp)}'\n")
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0",
                        "-i", flist_path,
                        "-c", "copy",
                        "-ar", "22050", "-ac", "1",
                        concat_wav,
                    ],
                    check=True, capture_output=True,
                )
            finally:
                os.unlink(flist_path)

        # Stage 2: WAV → MP3 with accurate Xing header so browsers show correct duration
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", concat_wav,
                    "-codec:a", "libmp3lame",
                    "-b:a", "128k",   # 128k is plenty for voice; saves ~30% space vs 192k
                    "-ar", "22050",
                    "-ac", "1",       # mono — narration, saves space, no stereo benefit
                    "-write_xing", "1",
                    output_mp3,
                ],
                check=True, capture_output=True,
            )
        finally:
            # Delete intermediate WAV only if we created it (not when single wav passed through)
            if len(wav_paths) != 1:
                try:
                    os.unlink(concat_wav)
                except OSError:
                    pass

        return output_mp3

    def _cleanup_chunks(self, wav_paths: list[str]) -> None:
        for p in wav_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Timing estimation
    # ------------------------------------------------------------------

    def _extract_word_timings(self, audio_path: str, raw_script: str) -> list[dict]:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            check=True, capture_output=True, text=True,
        )
        probe_data = json.loads(result.stdout)
        total_duration = float(probe_data["format"]["duration"])

        # Parse sections from raw script (## [SECTION NAME] headers)
        _SECTION_HEADER_RE = re.compile(r"^##\s*\[(.+?)\]\s*$", re.MULTILINE)
        section_splits = _SECTION_HEADER_RE.split(raw_script)
        # section_splits: [preamble, name1, body1, name2, body2, ...]

        # Build (section_name, paragraph_text) pairs
        all_paras: list[tuple[str, str]] = []
        # preamble paragraphs (before first section header) — section = ""
        preamble = section_splits[0]
        for p in re.split(r"\n\n+", self._clean_for_tts(preamble, keep_pauses=False)):
            if p.strip():
                all_paras.append(("", p.strip()))

        it = iter(section_splits[1:])
        for sec_name, body in zip(it, it):
            clean_body = self._clean_for_tts(body, keep_pauses=False)
            for p in re.split(r"\n\n+", clean_body):
                if p.strip():
                    all_paras.append((sec_name.strip().upper(), p.strip()))

        # Total word count across all paragraphs for proportional time allocation
        total_words = sum(len(p.split()) for _, p in all_paras) or 1
        secs_per_word = total_duration / total_words

        timings: list[dict] = []
        cursor = 0.0
        for idx, (section, para) in enumerate(all_paras):
            para_words = len(para.split())
            duration = para_words * secs_per_word
            preview = para[:60] + ("..." if len(para) > 60 else "")
            timings.append({
                "segment_idx": idx,
                "section": section,
                "text_preview": preview,
                "start_sec": round(cursor, 3),
                "end_sec": round(cursor + duration, 3),
            })
            cursor += duration

        return timings

    def _save_timings(self, timings: list[dict], path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(timings, fh, indent=2, ensure_ascii=False)
        return path
