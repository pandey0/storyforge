from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from src.db.models import Case, CaseCharacter
from src.db.session import get_session

# Cap controls image-gen spend per episode. google/gemini-2.5-flash-image via
# OpenRouter runs ~$0.0003/image (vs DALL-E 3's ~$0.04-0.08) — 4 images keeps
# a single short under a cent.
_MAX_IMAGES_PER_EPISODE = 4

_SCENE_EXCERPT_CHARS = 120

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = "google/gemini-2.5-flash-image"

_PROMPT_SUFFIX = (
    "Realistic documentary-style scene illustration. Indian setting. "
    "Journalistic, respectful, non-sensational. Cinematic lighting. "
    "Vertical 9:16 portrait orientation. No text, no logo, no watermark."
)


class SceneImageAgent:
    """
    Generates scene-specific AI images for an episode short, anchored to the
    character extracted for the case (not a single reused static portrait).
    """

    def run(self, slug: str, topic_slug: str) -> list[dict]:
        self._warn_if_characters_unapproved(slug)

        if not self._openrouter_available():
            return []

        md_path = Path(f"data/cases/{slug}/shorts/{topic_slug}.md")
        if not md_path.exists():
            logger.warning("Episode script not found: {}", md_path)
            return []

        script_text = md_path.read_text(encoding="utf-8")

        timings_path = self._find_timings_file(md_path)
        if timings_path is not None:
            segments = self._segments_from_timings(self._load_timings(timings_path))
        else:
            segments = self._segments_from_script(script_text)

        if not segments:
            logger.warning("No segments derived for {}/{}", slug, topic_slug)
            return []

        characters = self._load_characters(slug)

        out_dir = Path(f"data/cases/{slug}/scene_images/{topic_slug}")

        candidates = self._select_segments(segments, characters)
        if not candidates:
            return []

        out_dir.mkdir(parents=True, exist_ok=True)
        manifest: list[dict] = []
        for seg, matched_char in candidates:
            entry = self._generate_for_segment(seg, matched_char, out_dir)
            if entry is not None:
                manifest.append(entry)

        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("SceneImageAgent: {} images written for {}/{}", len(manifest), slug, topic_slug)
        return manifest

    # ------------------------------------------------------------------
    # Advisory checkpoint gate (Phase 21C) — warns only, never blocks.
    # ------------------------------------------------------------------

    def _warn_if_characters_unapproved(self, slug: str) -> None:
        from src.pipeline.checkpoints import get_checkpoint

        try:
            with get_session() as session:
                case = session.query(Case).filter_by(slug=slug).first()
                case_id = str(case.id) if case else None
        except Exception as exc:
            logger.warning("Could not look up case for checkpoint check ({}): {}", slug, exc)
            return

        if not case_id:
            return

        checkpoint = get_checkpoint(case_id, "characters")
        if not checkpoint or checkpoint.get("status") != "human_approved":
            logger.warning(
                "Using unapproved character set for {} — consider reviewing /cases/{}/ characters tab",
                slug, slug,
            )

    # ------------------------------------------------------------------
    # Availability check — graceful degradation, no partial work
    # ------------------------------------------------------------------

    def _openrouter_available(self) -> bool:
        if not os.environ.get("OPENROUTER_API_KEY"):
            logger.warning("OPENROUTER_API_KEY not set — skipping scene image generation")
            return False
        return True

    # ------------------------------------------------------------------
    # Segment loading — mirrors shorts_assembler_agent's lookup style
    # ------------------------------------------------------------------

    def _find_timings_file(self, md_path: Path) -> Optional[Path]:
        stem = md_path.stem
        parent = md_path.parent

        candidate_1 = parent / f"{stem}_timings.json"
        if candidate_1.exists():
            return candidate_1

        candidate_2 = parent / f"{stem}.json"
        if candidate_2.exists():
            return candidate_2

        logger.warning("No timings file found for {} — falling back to script split", stem)
        return None

    def _load_timings(self, timings_path: Path) -> list[dict]:
        try:
            with timings_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                logger.warning("Timings file is not a JSON list: {}", timings_path)
                return []
            return data
        except Exception as exc:
            logger.warning("Failed to read timings file {}: {}", timings_path, exc)
            return []

    def _segments_from_timings(self, timings: list[dict]) -> list[dict]:
        segments: list[dict] = []
        for i, seg in enumerate(timings):
            text = str(seg.get("text_preview", "")).strip()
            if not text:
                continue
            segments.append({
                "index": i,
                "start": seg.get("start_sec"),
                "end": seg.get("end_sec"),
                "text": text,
            })
        return segments

    def _segments_from_script(self, script_text: str) -> list[dict]:
        # No timings means no TTS pass yet — split on pause markers first
        # since they mark intentional narrative beats; sentence split is the fallback.
        if "[PAUSE" in script_text:
            chunks = re.split(r"\[PAUSE[^\]]*\]", script_text)
        else:
            chunks = re.split(r"(?<=[.।])\s+", script_text)

        segments: list[dict] = []
        for i, chunk in enumerate(chunks):
            text = chunk.strip()
            if not text:
                continue
            segments.append({"index": i, "start": None, "end": None, "text": text})
        return segments

    # ------------------------------------------------------------------
    # Character loading + matching
    # ------------------------------------------------------------------

    def _load_characters(self, slug: str) -> list[dict]:
        with get_session() as session:
            case = session.query(Case).filter_by(slug=slug).first()
            if not case:
                return []
            chars = session.query(CaseCharacter).filter_by(case_id=case.id).all()
            return [{"name": c.name, "role": c.role, "notes": c.notes} for c in chars]

    def _match_character(self, text: str, characters: list[dict]) -> Optional[dict]:
        for char in characters:
            if char["name"] and char["name"] in text:
                return char
        return None

    def _select_segments(
        self, segments: list[dict], characters: list[dict]
    ) -> list[tuple[dict, Optional[dict]]]:
        last_idx = len(segments) - 1
        hook = segments[0]
        reveal = segments[last_idx]

        # Hook + reveal are always included — they carry the most viewer-retention
        # weight in a short (first 3s decides scroll-past; last frame drives CTA/replay).
        selected: list[tuple[dict, Optional[dict]]] = [
            (hook, self._match_character(hook["text"], characters)),
        ]
        if last_idx != 0:
            selected.append((reveal, self._match_character(reveal["text"], characters)))

        chosen_indices = {hook["index"], reveal["index"]}
        remaining_slots = _MAX_IMAGES_PER_EPISODE - len(selected)

        if remaining_slots > 0:
            for seg in segments:
                if seg["index"] in chosen_indices:
                    continue
                match = self._match_character(seg["text"], characters)
                if match is None:
                    continue
                selected.append((seg, match))
                chosen_indices.add(seg["index"])
                remaining_slots -= 1
                if remaining_slots <= 0:
                    break

        selected.sort(key=lambda pair: pair[0]["index"])
        return selected

    # ------------------------------------------------------------------
    # DALL-E generation
    # ------------------------------------------------------------------

    def _build_prompt(self, segment: dict, character: Optional[dict]) -> str:
        scene_excerpt = segment["text"][:_SCENE_EXCERPT_CHARS].strip()
        parts: list[str] = []
        if character is not None:
            char_desc = " ".join(
                p for p in [character.get("role"), (character.get("notes") or "")[:120]] if p
            ).strip()
            if char_desc:
                parts.append(f"Character context: {char_desc}.")
        parts.append(f"Scene: {scene_excerpt}.")
        parts.append(_PROMPT_SUFFIX)
        return " ".join(parts)

    def _generate_for_segment(
        self, segment: dict, character: Optional[dict], out_dir: Path
    ) -> Optional[dict]:
        prompt = self._build_prompt(segment, character)
        dest = out_dir / f"seg_{segment['index']:02d}.png"

        try:
            resp = httpx.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": ["image", "text"],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            images = data["choices"][0]["message"].get("images") or []
            if not images:
                logger.warning("OpenRouter returned no image for segment {}: {!r}", segment["index"], data)
                return None
            data_url = images[0]["image_url"]["url"]
            b64_payload = data_url.split(",", 1)[1] if "," in data_url else data_url
            dest.write_bytes(base64.b64decode(b64_payload))
            logger.info("Scene image saved: {}", dest)
            return {
                "segment_index": segment["index"],
                "start": segment["start"],
                "end": segment["end"],
                "image_path": str(dest),
            }
        except Exception as exc:
            logger.warning("Scene image generation failed for segment {}: {}", segment["index"], exc)
            return None
