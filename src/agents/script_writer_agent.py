from __future__ import annotations

import os
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from src.db.channel_profile import get_profile_for_case
from src.db.models import Case, ChannelProfile, Script
from src.db.session import get_session
from src.pipeline.research_loader import load_research as _load_research_file
from src.pipeline.state import CaseState


class ScriptWriterAgent:
    def __init__(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        import google.generativeai as genai
        genai.configure(api_key=api_key)

    def run(self, state: CaseState) -> CaseState:
        logger.info(f"ScriptWriterAgent starting | case={state.slug}")

        profile = get_profile_for_case(state.slug)
        research = self._load_research(state)
        fix_notes = self._load_fix_notes(state.slug)

        with get_session() as session:
            case = session.query(Case).filter_by(slug=state.slug).one()
            user_prompt = self._build_prompt(research, case, profile, fix_notes=fix_notes)

        word_min, word_max = profile.word_count_range
        script = self._call_gemini(user_prompt, profile)

        if not self._validate_structure(script, profile.section_headers) or not (word_min <= self._count_words(script) <= word_max):
            logger.warning("Validation failed — retrying once")
            script = self._call_gemini("पुनरीक्षण आवश्यक:\n\n" + user_prompt, profile)
            if not self._validate_structure(script, profile.section_headers):
                logger.error("Second attempt also failed structure validation — saving anyway")
            if not (word_min <= self._count_words(script) <= word_max):
                logger.error(f"Word count out of range after retry: {self._count_words(script)}")

        draft_path = self._save_draft(state, script)
        state.draft_script_path = draft_path
        logger.info(f"Draft saved | path={draft_path} | words={self._count_words(script)}")

        # Clear fix_notes after successful fix run
        if fix_notes:
            self._clear_fix_notes(state.slug)

        with get_session() as session:
            db_script = self._save_to_db(state, script, session, profile)
            case = session.query(Case).filter_by(slug=state.slug).one()
            case.status = "human_review"
            logger.info(f"DB updated | script_id={db_script.id} | case.status=human_review")

        return state

    def _load_fix_notes(self, slug: str) -> str | None:
        """Load QA fix notes saved by the review UI, if any."""
        config_path = Path(f"data/cases/{slug}/configs/script_config.json")
        if not config_path.exists():
            return None
        import json as _json
        try:
            cfg = _json.loads(config_path.read_text())
            if cfg.get("fix_mode") and cfg.get("fix_notes"):
                return str(cfg["fix_notes"])
        except Exception:
            pass
        return None

    def _clear_fix_notes(self, slug: str) -> None:
        config_path = Path(f"data/cases/{slug}/configs/script_config.json")
        if not config_path.exists():
            return
        import json as _json
        try:
            cfg = _json.loads(config_path.read_text())
            cfg.pop("fix_mode", None)
            cfg.pop("fix_notes", None)
            config_path.write_text(_json.dumps(cfg, indent=2))
        except Exception:
            pass

    def _load_research(self, state: CaseState) -> dict:
        # Uses slug, not state.research_path — load_research() checks
        # research_manual.json first so a human override always takes effect,
        # regardless of which on-disk path case_research_agent recorded on state.
        return _load_research_file(state.slug)

    def _build_prompt(self, research: dict, case, profile: ChannelProfile, fix_notes: str | None = None) -> str:
        subject_age = str(case.extra.get("subject_age", "अज्ञात"))
        subject_name = case.subject_name or "अज्ञात"
        subject_role = case.extra.get("subject_role", "अज्ञात पेशा")
        year = str(case.year_of_crime) if case.year_of_crime else "अज्ञात"
        location = case.location or "अज्ञात स्थान"

        sources = research.get("sources", {})

        wiki = sources.get("wikipedia", {}) or {}
        wikipedia_raw: str = wiki.get("extract_full") or wiki.get("extract_summary") or ""
        wikipedia_extract = wikipedia_raw[:3000]

        judgments = sources.get("indian_kanoon", []) or []
        judgment_blocks: list[str] = []
        for j in judgments[:3]:
            title = j.get("title", "अज्ञात निर्णय")
            headline = j.get("headline", j.get("content", ""))[:500]
            judgment_blocks.append(f"शीर्षक: {title}\n{headline}")
        judgments_text = "\n\n".join(judgment_blocks) if judgment_blocks else "कोई अदालती निर्णय उपलब्ध नहीं।"

        articles = sources.get("news_archive", []) or []
        article_blocks: list[str] = []
        for a in articles[:5]:
            title = a.get("title", "अज्ञात")
            content_preview = (a.get("content", "") or "")[:200]
            article_blocks.append(f"- {title}\n  {content_preview}")
        articles_text = "\n\n".join(article_blocks) if article_blocks else "कोई समाचार लेख उपलब्ध नहीं।"

        fix_section = ""
        if fix_notes:
            # Load existing draft for targeted fix
            draft_path = Path(f"data/cases/{case.slug}/script_draft.md")
            manual_path = Path(f"data/cases/{case.slug}/script_manual.md")
            existing = ""
            for p in [manual_path, draft_path]:
                if p.exists():
                    existing = p.read_text(encoding="utf-8")[:12000]
                    break
            if existing:
                fix_section = (
                    f"\n\n--- मौजूदा स्क्रिप्ट (सुधार करें) ---\n{existing}\n\n"
                    f"--- QA समीक्षक की टिप्पणियाँ (इन्हें ठीक करें) ---\n{fix_notes}\n\n"
                    f"ऊपर दी गई स्क्रिप्ट को QA टिप्पणियों के आधार पर सुधारें। "
                    f"केवल आवश्यक बदलाव करें, बाकी स्क्रिप्ट वैसी ही रखें।"
                )

        base_instruction = (
            "अब पूरी हिंदी डॉक्युमेंट्री स्क्रिप्ट लिखें।"
            if not fix_section
            else ""
        )

        return profile.case_prompt_template.format(
            case_name=case.name,
            subject_name=subject_name,
            subject_age=subject_age,
            subject_role=subject_role,
            year=year,
            location=location,
            wikipedia_extract=wikipedia_extract,
            judgments_text=judgments_text,
            articles_text=articles_text,
            fix_section=fix_section,
            base_instruction=base_instruction,
        )

    def _call_gemini(self, user_prompt: str, profile: ChannelProfile) -> str:
        import google.generativeai as genai

        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=profile.voice_system_prompt,
        )
        logger.info("Calling Gemini 2.5 Flash | max_tokens=8192")
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.75,
                max_output_tokens=8192,
            ),
        )
        logger.info(f"Gemini response received | chars={len(response.text)}")
        return response.text

    def _validate_structure(self, script: str, section_headers: list[str]) -> bool:
        missing = [h for h in section_headers if h not in script]
        if missing:
            logger.warning(f"Missing section headers: {missing}")
            return False
        return True

    def _count_words(self, script: str) -> int:
        return len(script.split())

    def _save_draft(self, state: CaseState, script: str) -> str:
        draft_dir = Path(f"data/cases/{state.slug}")
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / "script_draft.md"
        draft_path.write_text(script, encoding="utf-8")
        return str(draft_path)

    def _save_to_db(self, state: CaseState, script: str, session: Session, profile: ChannelProfile) -> Script:
        word_count = self._count_words(script)
        duration_est = round(word_count / profile.words_per_minute, 2)

        existing = (
            session.query(Script)
            .filter_by(case_id=state.case_id)
            .order_by(Script.version.desc())
            .first()
        )
        next_version = (existing.version or 0) + 1 if existing else 1

        db_script = Script(
            case_id=state.case_id,
            version=next_version,
            script_text=script,
            word_count=word_count,
            duration_est_min=duration_est,
            status="draft",
        )
        session.add(db_script)
        session.flush()
        logger.info(f"Script saved to DB | version={next_version} | words={word_count} | est={duration_est}min")
        return db_script
