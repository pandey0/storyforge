from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

import requests
from loguru import logger
from sqlalchemy import select

from src.agents.character_agent import CharacterAgent
from src.db.models import BRollCache, Case
from src.db.session import get_session
from src.pipeline.state import CaseState

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

INDIAN_CITIES = {
    "Delhi", "Mumbai", "Kolkata", "Chennai", "Bangalore", "Bengaluru",
    "Hyderabad", "Pune", "Ahmedabad", "Jaipur", "Noida", "Gurgaon",
    "Lucknow", "Chandigarh", "Bhopal",
}

# Markers to strip before keyword extraction — these are TTS/script markers, not content
_STRIP_BEFORE_KEYWORDS_RE = re.compile(
    r"\[(?:PAUSE\s*[\d.]+\s*s|SLOW|FAST|DRAMATIC|NORMAL|SOURCE:[^\]]*)\]",
    re.IGNORECASE,
)


class BRollAgent:
    def run(self, state: CaseState, script_path: str = None) -> CaseState:
        path = script_path or state.script_path or state.draft_script_path
        if not path or not Path(path).exists():
            logger.warning(f"BRollAgent: no script found for {state.slug}")
            state.error = "broll: script not found"
            return state

        script_text = Path(path).read_text(encoding="utf-8")
        segments = self.extract_segments(script_text)

        broll_dir = f"data/cases/{state.slug}/broll/"
        Path(broll_dir).mkdir(parents=True, exist_ok=True)

        # Load character images — these take priority over stock footage
        char_image_map = CharacterAgent().get_character_image_map(state.slug)
        logger.info(f"BRollAgent: {len(char_image_map)} character images available")

        for idx, segment in enumerate(segments):
            try:
                # 1. Check if any character appears in this segment
                char_path = self._match_character_image(segment["text"], char_image_map)
                if char_path:
                    segment["clip_path"] = char_path
                    logger.info(f"BRollAgent: character image → {char_path} for [{segment['section']}]")
                    continue

                # 2. Stock footage (Pexels / Pixabay)
                clip_path = self.fetch_for_segment(segment, state.slug)
                if clip_path:
                    segment["clip_path"] = clip_path
                else:
                    logger.warning(
                        f"BRollAgent: no clip for segment [{segment['section']}] query='{segment['query']}'"
                    )
            except Exception as exc:
                logger.warning(f"BRollAgent: error fetching segment {idx}: {exc}")

        state.broll_dir = broll_dir

        with get_session() as session:
            case = session.execute(
                select(Case).where(Case.slug == state.slug)
            ).scalar_one_or_none()
            if case:
                case.status = "video"
                state.status = "video"

        return state

    def extract_segments(self, script_text: str, default_location: str | None = None) -> list[dict]:
        sections = re.split(r"^##\s+\[(.+?)\]", script_text, flags=re.MULTILINE)
        segments = []

        if not sections:
            return segments

        # sections[0] is preamble, then alternating section_name / body
        it = iter(sections[1:])
        for section_name, body in zip(it, it):
            section = section_name.strip()
            # Strip TTS control markers so they don't bleed into keyword extraction
            text_clean = _STRIP_BEFORE_KEYWORDS_RE.sub("", body).strip()

            words = text_clean.split()
            duration_est = len(words) / 150 * 60

            keywords = self._extract_keywords(text_clean)
            location = self._extract_location(text_clean) or default_location
            query = self.keyword_to_query(keywords, section, location)

            segments.append({
                "section": section,
                "text": text_clean,
                "keywords": keywords,
                "duration_est": round(duration_est, 1),
                "query": query,
                "location": location,
            })

        return segments

    def _extract_keywords(self, text: str) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()

        for word in re.findall(r"\b[A-Z][a-zA-Z]+\b", text):
            if word not in seen:
                seen.add(word)
                keywords.append(word)

        for city in INDIAN_CITIES:
            if city.lower() in text.lower() and city not in seen:
                seen.add(city)
                keywords.append(city)

        return keywords[:10]

    def _extract_location(self, text: str) -> Optional[str]:
        for city in INDIAN_CITIES:
            if re.search(rf"\b{city}\b", text, re.IGNORECASE):
                return city
        return None

    def keyword_to_query(self, keywords: list[str], section: str, location: Optional[str]) -> str:
        """Build a Pexels search query from section name + keywords. No hardcoded niche."""
        # Clean section name: "THE CRIME" → "the crime", "COLD OPEN" → "cold open"
        section_words = section.lower().replace("_", " ").strip()
        loc = location or ""
        kw = " ".join(keywords[:2]) if keywords else ""
        parts = [p for p in [loc, kw, section_words] if p]
        return " ".join(parts)[:100]

    def search_pexels(self, query: str, duration_min: int = 5) -> list[dict]:
        if not PEXELS_API_KEY:
            logger.warning("BRollAgent: PEXELS_API_KEY not set")
            return []

        url = "https://api.pexels.com/videos/search"
        params = {
            "query": query,
            "per_page": 5,
            "orientation": "landscape",
            "min_duration": duration_min,
        }
        headers = {"Authorization": PEXELS_API_KEY}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"BRollAgent: Pexels search failed for '{query}': {exc}")
            return []

        results = []
        for video in data.get("videos", []):
            best_file = self._best_pexels_file(video.get("video_files", []))
            if not best_file:
                continue
            results.append({
                "id": str(video.get("id", "")),
                "url": video.get("url", ""),
                "duration": video.get("duration", 0),
                "width": best_file.get("width", 0),
                "height": best_file.get("height", 0),
                "download_url": best_file.get("link", ""),
            })
        return results

    def _best_pexels_file(self, files: list[dict]) -> Optional[dict]:
        hd = [f for f in files if f.get("quality") in ("hd", "uhd") and f.get("link")]
        if hd:
            return max(hd, key=lambda f: f.get("width", 0) * f.get("height", 0))
        valid = [f for f in files if f.get("link")]
        if valid:
            return max(valid, key=lambda f: f.get("width", 0) * f.get("height", 0))
        return None

    def download_clip(self, url: str, dest_path: str) -> str:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fh.write(chunk)
        return dest_path

    def get_cached(self, query: str) -> Optional[str]:
        with get_session() as session:
            row = session.execute(
                select(BRollCache).where(BRollCache.query == query)
            ).scalar_one_or_none()
            if row and row.file_path and Path(row.file_path).exists():
                return row.file_path
        return None

    def cache_clip(
        self,
        query: str,
        file_path: str,
        source: str,
        source_id: str,
        duration: float,
    ) -> None:
        try:
            size_mb = Path(file_path).stat().st_size / (1024 * 1024) if Path(file_path).exists() else None
        except OSError:
            size_mb = None

        with get_session() as session:
            entry = BRollCache(
                query=query,
                file_path=file_path,
                source=source,
                source_id=source_id,
                duration_sec=duration,
                file_size_mb=size_mb,
            )
            session.add(entry)

    def fetch_for_segment(self, segment: dict, slug: str) -> Optional[str]:
        query = segment["query"]
        section = segment["section"]
        duration_est = segment.get("duration_est", 10.0)
        section_safe = re.sub(r"[^a-zA-Z0-9_]", "_", section).lower()

        cached = self.get_cached(query)
        if cached:
            logger.info(f"B-roll: cache hit '{query}' → {cached}")
            return cached

        clips = self.search_pexels(query, duration_min=max(5, int(duration_est / 4)))
        time.sleep(1)

        if not clips:
            logger.warning(f"BRollAgent: no clips found for query='{query}'")
            return None

        best = self._pick_best_clip(clips, duration_est)
        download_url = best["download_url"]
        if not download_url:
            logger.warning(f"BRollAgent: no download URL for query='{query}'")
            return None

        broll_dir = Path(f"data/cases/{slug}/broll")
        broll_dir.mkdir(parents=True, exist_ok=True)
        dest = str(broll_dir / f"{section_safe}.mp4")

        try:
            self.download_clip(download_url, dest)
        except Exception as exc:
            logger.warning(f"BRollAgent: download failed for '{query}': {exc}")
            return None

        duration = float(best.get("duration", 0))
        self.cache_clip(query, dest, "pexels", best["id"], duration)

        logger.info(f"B-roll: fetched '{query}' → {dest} ({duration}s, pexels)")
        return dest

    def fetch_for_shorts_topic(self, slug: str, topic_slug: str, query: str) -> Optional[str]:
        # shorts_assembler_agent._pick_broll() looks up broll/{topic_slug}.mp4 directly,
        # so the destination filename must be exact, not derived from the query/section.
        broll_dir = Path(f"data/cases/{slug}/broll")
        broll_dir.mkdir(parents=True, exist_ok=True)
        dest = str(broll_dir / f"{topic_slug}.mp4")

        if Path(dest).exists():
            logger.info(f"B-roll shorts: '{topic_slug}' already exists → {dest}")
            return dest

        cached = self.get_cached(query)
        if cached:
            shutil.copy2(cached, dest)
            logger.info(f"B-roll shorts: cache hit '{query}' → copied to {dest}")
            return dest

        clips = self.search_pexels(query, duration_min=8)
        if not clips:
            logger.warning(f"BRollAgent: no clips found for shorts topic='{topic_slug}' query='{query}'")
            return None

        best = max(clips, key=lambda c: c.get("width", 0) * c.get("height", 0))
        download_url = best["download_url"]
        if not download_url:
            logger.warning(f"BRollAgent: no download URL for shorts topic='{topic_slug}' query='{query}'")
            return None

        try:
            self.download_clip(download_url, dest)
        except Exception as exc:
            logger.warning(f"BRollAgent: download failed for shorts topic='{topic_slug}': {exc}")
            return None

        duration = float(best.get("duration", 0))
        self.cache_clip(query, dest, "pexels", best["id"], duration)

        logger.info(f"B-roll shorts: fetched '{query}' → {dest} ({duration}s, pexels)")
        return dest

    def _match_character_image(self, segment_text: str, char_map: dict[str, str]) -> Optional[str]:
        """Return image path if any known character name appears in this segment."""
        for name, path in char_map.items():
            if name.lower() in segment_text.lower():
                return path
        return None

    def _pick_best_clip(self, clips: list[dict], duration_est: float) -> dict:
        def score(clip: dict) -> float:
            pixels = clip.get("width", 0) * clip.get("height", 0)
            dur = clip.get("duration", 0)
            dur_diff = abs(dur - duration_est)
            dur_score = 1.0 / (1.0 + dur_diff)
            return pixels * 0.6 + dur_score * 100000 * 0.4

        return max(clips, key=score)
