from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from loguru import logger

from src.db.channel_profile import get_profile_for_case
from src.db.models import Case, CaseCharacter
from src.db.session import get_session
from src.pipeline.research_loader import load_research as _load_research_file
from src.pipeline.state import CaseState

# Latin proper names (English)
_NAME_RE_LATIN = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")

# Devanagari word: one or more Devanagari chars (including nukta, anusvara etc.)
_DEVANAGARI_WORD = re.compile(r"[ऀ-ॿ‌‍]+")

# Common Hindi name suffixes (surname indicators) — helps filter real names
_HINDI_NAME_SUFFIXES = {
    "शर्मा", "वर्मा", "गुप्ता", "सिंह", "कुमार", "देवी", "लाल", "राय",
    "खान", "अली", "जोशी", "पाटिल", "रेड्डी", "नायर", "पिल्लई", "मेनन",
    "रमानी", "वशिष्ठ", "गांधी", "नेहरू", "चौधरी", "मिश्रा", "त्रिपाठी",
    "पांडे", "तिवारी", "दीक्षित", "श्रीवास्तव", "अग्रवाल", "बंसल",
}

# Kept hardcoded (not moved to ChannelProfile.entity_roles): a tightly-coupled
# victim/accused disambiguation heuristic, not a general role taxonomy.
# These words are near-definitive — if they appear near a name, that role wins
ROLE_STRONG_SIGNALS = {
    # Only signals that can ONLY apply to an accused (not victim)
    "accused": {"हत्यारा", "क़ातिल", "कातिल", "आरोपी", "गिरफ़्तार", "सज़ा", "दोषी",
                "ने गोली", "ने गोली मारी"},  # "ne goli mari" = "he shot" → shooter only
    # Signals that only apply to a victim
    "victim":  {"पीड़ित", "मृतक", "की हत्या", "हत्या की शिकार", "को गोली"},  # "ko goli" = "was shot"
}


class CharacterAgent:
    """
    Extracts named characters from research + script.
    Stores to DB + creates placeholder entries in data/cases/{slug}/characters/.
    Dashboard then lets user upload photos per character.
    """

    def run(self, state: CaseState) -> CaseState:
        profile = get_profile_for_case(state.slug)
        entity_roles = profile.entity_roles
        research = self._load_research(state)
        script = self._load_script(state)

        # Research is authoritative — extract first
        characters = self._extract_from_research(research, entity_roles)
        research_names_lower = {n.lower() for n in characters}

        # Script supplements — only add names not already in research
        script_chars = self._extract_from_script(script, research, entity_roles)
        for name, meta in script_chars.items():
            if name.lower() not in research_names_lower:
                characters[name] = meta

        chars_dir = Path(f"data/cases/{state.slug}/characters")
        chars_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            case = session.query(Case).filter_by(slug=state.slug).one()
            existing_chars = {c.name: c for c in session.query(CaseCharacter).filter_by(case_id=case.id).all()}

            for name, meta in characters.items():
                if name in existing_chars:
                    # Update role/notes only if currently empty
                    existing = existing_chars[name]
                    if not existing.role and meta.get("role"):
                        existing.role = meta["role"]
                        logger.info(f"Updated role for existing character: {name} → {meta['role']}")
                    if not existing.notes and meta.get("notes"):
                        existing.notes = meta["notes"]
                else:
                    row = CaseCharacter(
                        id=uuid.uuid4(),
                        case_id=case.id,
                        name=name,
                        role=meta.get("role"),
                        notes=meta.get("notes"),
                    )
                    session.add(row)
                    logger.info(f"Character added: {name} ({meta.get('role')})")

        logger.info(f"CharacterAgent: {len(characters)} characters extracted for {state.slug}")

        # Phase 3: AI portraits for characters without images
        with get_session() as session:
            case = session.query(Case).filter_by(slug=state.slug).one()
            all_chars = session.query(CaseCharacter).filter_by(case_id=case.id).all()
            needs_portrait = [
                (c.id, c.name, c.role, c.notes)
                for c in all_chars
                if not c.image_path or not Path(c.image_path).exists()
            ]

        for char_id, name, role, notes in needs_portrait:
            self._generate_ai_portrait(state.slug, char_id, name, role, notes, chars_dir)

        return state

    def _generate_ai_portrait(
        self,
        slug: str,
        char_id: uuid.UUID,
        name: str,
        role: Optional[str],
        notes: Optional[str],
        chars_dir: Path,
    ) -> Optional[str]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — skipping AI portrait for %s", name)
            return None
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("openai package not installed — skipping AI portrait for %s", name)
            return None

        _ROLE_DESC = {
            "victim":  "innocent person who became a victim of crime",
            "accused": "person accused in a criminal case",
            "judge":   "senior Indian judge in formal judicial attire",
            "lawyer":  "Indian lawyer in black court robes",
            "witness": "ordinary Indian citizen called as witness",
            "police":  "Indian police officer in khaki uniform",
            "family":  "ordinary Indian person, family member",
        }
        role_desc = _ROLE_DESC.get(role or "", "ordinary Indian person")
        context = (notes or "")[:80].strip()
        prompt = (
            f"Realistic, dignified documentary portrait illustration of an Indian person. "
            f"Role: {role_desc}. {context}. "
            f"Neutral dark studio background. Journalistic documentary style. "
            f"Respectful, non-sensational. No text, no logo, no watermark. "
            f"Cinematic lighting. Single subject, facing camera."
        )

        try:
            client = OpenAI(api_key=api_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            img_url = response.data[0].url
            safe_name = re.sub(r"[^\w]", "_", name.lower())
            dest = chars_dir / f"{safe_name}_ai_portrait.png"
            img_resp = requests.get(img_url, timeout=60)
            img_resp.raise_for_status()
            dest.write_bytes(img_resp.content)

            with get_session() as session:
                char = session.query(CaseCharacter).filter_by(id=char_id).first()
                if char:
                    char.image_path = str(dest)
                    char.image_url = img_url

            logger.info("AI portrait saved: %s", dest)
            return str(dest)
        except Exception as exc:
            logger.warning("AI portrait failed for %s: %s", name, exc)
            return None

    def add_image_from_url(self, slug: str, name: str, url: str) -> str:
        """Download image from URL, save to characters dir, update DB."""
        chars_dir = Path(f"data/cases/{slug}/characters")
        chars_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(urlparse(url).path).suffix or ".jpg"
        safe_name = re.sub(r"[^\w]", "_", name.lower())
        dest = chars_dir / f"{safe_name}{ext}"

        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1024 * 64):
                fh.write(chunk)

        with get_session() as session:
            case = session.query(Case).filter_by(slug=slug).one()
            char = (
                session.query(CaseCharacter)
                .filter_by(case_id=case.id, name=name)
                .first()
            )
            if char:
                char.image_path = str(dest)
                char.image_url = url
            else:
                session.add(CaseCharacter(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    name=name,
                    image_path=str(dest),
                    image_url=url,
                ))

        logger.info(f"Character image saved: {dest}")
        return str(dest)

    def add_image_from_file(self, slug: str, name: str, src_path: str) -> str:
        """Copy uploaded image to characters dir, update DB."""
        import shutil
        chars_dir = Path(f"data/cases/{slug}/characters")
        chars_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(src_path).suffix or ".jpg"
        safe_name = re.sub(r"[^\w]", "_", name.lower())
        dest = chars_dir / f"{safe_name}{ext}"
        shutil.copy2(src_path, dest)

        with get_session() as session:
            case = session.query(Case).filter_by(slug=slug).one()
            char = (
                session.query(CaseCharacter)
                .filter_by(case_id=case.id, name=name)
                .first()
            )
            if char:
                char.image_path = str(dest)
            else:
                session.add(CaseCharacter(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    name=name,
                    image_path=str(dest),
                ))

        return str(dest)

    def get_character_image_map(self, slug: str) -> dict[str, str]:
        """Return {character_name: image_path} for all characters with images."""
        with get_session() as session:
            case = session.query(Case).filter_by(slug=slug).first()
            if not case:
                return {}
            chars = (
                session.query(CaseCharacter)
                .filter_by(case_id=case.id)
                .all()
            )
            result = {}
            for c in chars:
                if c.image_path and Path(c.image_path).exists():
                    result[c.name] = c.image_path
            return result

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _load_research(self, state: CaseState) -> dict:
        try:
            return _load_research_file(state.slug)
        except ValueError:
            return {}

    def _load_script(self, state: CaseState) -> str:
        for p in [
            f"data/cases/{state.slug}/script_manual.md",
            state.script_path,
            state.draft_script_path,
        ]:
            if p and Path(p).exists():
                return Path(p).read_text(encoding="utf-8")
        return ""

    def _normalize_role(self, role: str, entity_roles: list[dict]) -> Optional[str]:
        role = role.lower()
        for entry in entity_roles:
            if any(kw.lower() in role for kw in entry["keywords"]):
                return entry["slug"]
        if not role:
            return None
        # Research synthesis can hand back a long descriptive sentence
        # (e.g. "investigating agency, initially treated death as
        # suicide, ..."), but this column is a short display tag
        # (case_characters.role is varchar(100) in the DB) — take the
        # first clause and hard-truncate as a backstop. The full
        # description is preserved separately in the character's notes.
        short = role.split(",")[0].split(".")[0].strip()
        return (short or role)[:100]

    def _extract_from_research(self, research: dict, entity_roles: list[dict]) -> dict[str, dict]:
        chars: dict[str, dict] = {}

        # Primary: people_involved list (most complete source)
        for person in research.get("people_involved", []):
            name = (person.get("name") or "").strip()
            if not name or len(name) < 3:
                continue
            role = person.get("role", "").lower().strip()
            desc = person.get("description", "")
            # Normalize role to our standard set
            role = self._normalize_role(role, entity_roles)
            chars[name] = {"role": role, "notes": desc[:200] if desc else "From research.json people_involved"}

        # Fallback: summary.key_entities (if people_involved was empty)
        if not chars:
            summary = research.get("summary", {})
            if isinstance(summary, dict):
                for entity in summary.get("key_entities", []):
                    name = (entity.get("name") or "").strip()
                    if not name:
                        continue
                    raw_role = entity.get("role", "")
                    role = self._normalize_role(raw_role, entity_roles)
                    chars[name] = {"role": role, "notes": f"From research key_entities ({raw_role})"}

        return chars

    def _extract_from_script(self, script: str, research: dict, entity_roles: list[dict]) -> dict[str, dict]:
        chars: dict[str, dict] = {}
        if not script:
            return chars

        is_hindi = bool(re.search(r"[ऀ-ॿ]", script))

        if is_hindi:
            chars.update(self._extract_hindi_names(script, research, entity_roles))
        else:
            chars.update(self._extract_latin_names(script, research, entity_roles))

        return chars

    def _extract_latin_names(self, script: str, research: dict, entity_roles: list[dict]) -> dict[str, dict]:
        chars: dict[str, dict] = {}
        counts: dict[str, int] = {}
        for m in _NAME_RE_LATIN.finditer(script):
            name = m.group(1)
            if len(name) > 40:
                continue
            counts[name] = counts.get(name, 0) + 1
        for name, count in counts.items():
            if count < 2:
                continue
            role = self._infer_role(name, script, research, entity_roles)
            chars[name] = {"role": role, "notes": f"Mentioned {count}x in script"}
        return chars

    def _extract_hindi_names(self, script: str, research: dict, entity_roles: list[dict]) -> dict[str, dict]:
        """
        Extract person names from Hindi script using two strategies:
        1. Devanagari 2-word sequences where second word is a known surname suffix
        2. Single Devanagari words that appear as known suffixes (first-name only mentions)
        Both filtered by frequency (2+ occurrences).
        """
        chars: dict[str, dict] = {}

        # Tokenise into Devanagari words
        words = _DEVANAGARI_WORD.findall(script)

        # Strategy 1: "FirstName Surname" bigrams where surname is known
        bigram_counts: dict[str, int] = {}
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w2 in _HINDI_NAME_SUFFIXES and 2 <= len(w1) <= 15:
                full = f"{w1} {w2}"
                bigram_counts[full] = bigram_counts.get(full, 0) + 1

        for name, count in bigram_counts.items():
            if count >= 2:
                role = self._infer_role(name, script, research, entity_roles)
                chars[name] = {"role": role, "notes": f"Mentioned {count}x in script"}

        # Strategy 2: First-name only — if a known surname appears in script,
        # also count standalone first-name occurrences already covered by bigram.
        # Additionally, pull names directly from research key_entities.
        summary = research.get("summary", {})
        if isinstance(summary, dict):
            for entity in summary.get("key_entities", []):
                val = (entity.get("name") or "").strip()
                role = self._normalize_role(entity.get("role", ""), entity_roles)
                if val and val not in chars:
                    count = script.count(val)
                    if count == 0:
                        # Try first name only
                        fname = val.split()[0] if " " in val else val
                        count = script.count(fname)
                        if count >= 2:
                            chars[val] = {"role": role, "notes": f"From research, first-name mentioned {count}x"}
                    elif count >= 1:
                        chars[val] = {"role": role, "notes": f"From research, mentioned {count}x"}

        return chars

    def _infer_role(self, name: str, script: str, research: dict, entity_roles: list[dict]) -> Optional[str]:
        summary = research.get("summary", {})
        key_entities = summary.get("key_entities", []) if isinstance(summary, dict) else []
        for entity in key_entities:
            if name == entity.get("name"):
                return self._normalize_role(entity.get("role", ""), entity_roles)

        # Collect all occurrences, check context around each
        role_scores: dict[str, int] = {}
        strong_hits: dict[str, int] = {}
        start = 0
        while True:
            idx = script.find(name, start)
            if idx == -1:
                break
            context = script[max(0, idx - 150):idx + 150].lower()
            for entry in entity_roles:
                if any(kw in context for kw in entry["keywords"]):
                    role_scores[entry["slug"]] = role_scores.get(entry["slug"], 0) + 1
            # Check strong signals — these override weak frequency wins
            for role, signals in ROLE_STRONG_SIGNALS.items():
                if any(sig in context for sig in signals):
                    strong_hits[role] = strong_hits.get(role, 0) + 1
            start = idx + 1

        # Strong signals override everything
        if strong_hits:
            return max(strong_hits, key=strong_hits.get)

        if role_scores:
            return max(role_scores, key=role_scores.get)

        # Cross-check: if name contains/matches a key_entity name fragment
        for entity in key_entities:
            ent_name = (entity.get("name") or "").lower()
            if not ent_name:
                continue
            ent_parts = ent_name.split()
            if any(p in name.lower() for p in ent_parts if len(p) > 2):
                return self._normalize_role(entity.get("role", ""), entity_roles)

        return None
