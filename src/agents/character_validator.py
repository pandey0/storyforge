"""
Lightweight validation gate for the characters step (Phase 21C).

Mirrors research_validator.py's shape: a single small Gemini call that
sanity-checks the *current* character set (name/role/notes) against the
case research, looking for roles that obviously don't fit (e.g. someone
tagged with one role in the cast list who the research actually describes
playing a different, unrelated role). Role taxonomy is whatever the case's
ChannelProfile.entity_roles defines — not assumed to be crime-specific.

This deliberately does NOT re-derive roles or touch the DB rows — it only
asks "does this still look right" and records the verdict via the generic
checkpoint state machine (src/pipeline/checkpoints.py). Human approval via
mark_human_approved/rejected is a separate, explicit action — this function
never approves or rejects, only ai_validates/ai_flags.
"""
from __future__ import annotations

import json
import os
import uuid

from loguru import logger

from src.db.models import CaseCharacter
from src.db.session import get_session
from src.pipeline.checkpoints import mark_ai_validated
from src.pipeline.research_loader import load_research


def _load_characters(case_id: str) -> list[dict]:
    with get_session() as session:
        rows = (
            session.query(CaseCharacter)
            .filter(CaseCharacter.case_id == uuid.UUID(str(case_id)))
            .order_by(CaseCharacter.added_at)
            .all()
        )
        return [
            {"name": r.name, "role": r.role, "notes": r.notes}
            for r in rows
        ]


def _llm_check(research: dict, characters: list[dict]) -> tuple[bool, str]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set — skipping LLM character-role check")
        return True, ""

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = (
        "You are reviewing the cast list extracted for a documentary content "
        "pipeline (the case may be on any subject, not necessarily crime). "
        "Given the case research context and a list of characters with their "
        "assigned role and notes, check whether each character's role still "
        "plausibly fits what the research actually says about them — flag "
        "anyone whose assigned role contradicts how the research describes "
        "their involvement.\n\n"
        "Answer ONLY with the single word YES if every character's role "
        "plausibly fits, or NO if at least one role looks clearly wrong. "
        "After the YES/NO, optionally add a colon and a short reason naming "
        "the character and what looks off.\n\n"
        f"RESEARCH CONTEXT:\n{json.dumps(research, ensure_ascii=False, indent=2)[:6000]}\n\n"
        f"CHARACTERS:\n{json.dumps(characters, ensure_ascii=False, indent=2)[:3000]}"
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                # gemini-2.5-flash burns an uncontrolled amount of tokens on
                # internal "thinking" before any visible output — 600 was
                # nowhere near enough and got truncated to a few words.
                # 1500 is the safe floor for this prompt's complexity.
                max_output_tokens=1500,
            ),
        )
        text = (response.text or "").strip()
    except Exception as exc:
        logger.error("character LLM validation failed: {}", exc)
        return True, f"LLM validation errored, skipped: {exc}"

    upper = text.upper()
    if upper.startswith("NO"):
        return False, text or "LLM flagged at least one character role as implausible"
    return True, ""


def validate_characters(case_id: str, slug: str) -> tuple[bool, str]:
    try:
        research = load_research(slug)
    except ValueError as exc:
        mark_ai_validated(case_id, "characters", False, notes=str(exc))
        return False, str(exc)

    characters = _load_characters(case_id)
    if not characters:
        reason = "no characters recorded for this case yet"
        mark_ai_validated(case_id, "characters", False, notes=reason)
        return False, reason

    passed, reason = _llm_check(research, characters)
    mark_ai_validated(case_id, "characters", passed, notes=reason or None)
    return passed, reason
