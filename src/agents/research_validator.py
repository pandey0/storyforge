"""
Lightweight validation gate for the research step (Phase 21B).

Two tiers:
1. Always-run structural sanity check — no LLM call, just "is there
   actually some content here, not an empty shell."
2. If a human has hand-edited research_manual.json (checkpoint
   edited_by == "human"), an additional small Gemini call sanity-checks
   that the edit still reads like coherent case research and not
   corrupted/nonsensical/spam text.

This deliberately does NOT re-verify facts — that's qa_agent.py's job for
scripts. This is just "is this still a real research file."
"""
from __future__ import annotations

import os

from loguru import logger

from src.pipeline.checkpoints import get_checkpoint, mark_ai_validated
from src.pipeline.research_loader import load_research


def _structural_check(research: dict) -> tuple[bool, str]:
    case_name = (research.get("case_name") or "").strip()
    if not case_name:
        return False, "research is missing a non-empty case_name"

    summary = research.get("summary") or {}
    has_summary_content = bool(
        isinstance(summary, dict)
        and (
            (summary.get("subject") or "").strip()
            or summary.get("year")
            or (summary.get("location") or "").strip()
        )
    )

    sources = research.get("sources") or {}
    wiki = sources.get("wikipedia") or {}
    has_wiki = bool(
        isinstance(wiki, dict)
        and ((wiki.get("extract_summary") or "").strip() or (wiki.get("extract_full") or "").strip())
    )
    has_news = bool(sources.get("news_archive"))
    has_kanoon = bool(sources.get("indian_kanoon"))

    if not (has_summary_content or has_wiki or has_news or has_kanoon):
        return False, (
            "research has a case_name but no real content — "
            "summary fields, wikipedia extract, news_archive, and indian_kanoon are all empty"
        )

    return True, ""


def _llm_sanity_check(research: dict) -> tuple[bool, str]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set — skipping LLM sanity check for human-edited research")
        return True, ""

    import json

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = (
        "You are reviewing a JSON research file for a documentary content "
        "pipeline (the case may be on any subject — not necessarily crime). "
        "A human just hand-edited this file. Answer ONLY with the single "
        "word YES if it still looks like coherent, plausible case research "
        "(case name, summary, sources — normal prose/data, even if incomplete or "
        "terse), or NO if it looks corrupted, nonsensical, spam, or unrelated noise. "
        "After the YES/NO, optionally add a colon and a short reason.\n\n"
        f"RESEARCH JSON:\n{json.dumps(research, ensure_ascii=False, indent=2)[:8000]}"
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                # gemini-2.5-flash burns an uncontrolled amount of tokens on
                # internal "thinking" before any visible text — 500 was not
                # enough to get a visible answer back, learned the hard way.
                max_output_tokens=1500,
            ),
        )
        text = (response.text or "").strip()
    except Exception as exc:
        logger.error("research LLM sanity check failed: {}", exc)
        return True, f"LLM sanity check errored, skipped: {exc}"

    upper = text.upper()
    if upper.startswith("NO"):
        return False, text or "LLM flagged this research as nonsensical/corrupted"
    return True, ""


def validate_research(case_id: str, slug: str) -> tuple[bool, str]:
    try:
        research = load_research(slug)
    except ValueError as exc:
        mark_ai_validated(case_id, "research", False, notes=str(exc))
        return False, str(exc)

    passed, reason = _structural_check(research)
    if not passed:
        mark_ai_validated(case_id, "research", False, notes=reason)
        return False, reason

    checkpoint = get_checkpoint(case_id, "research")
    if checkpoint and checkpoint.get("edited_by") == "human":
        passed, reason = _llm_sanity_check(research)
        if not passed:
            mark_ai_validated(case_id, "research", False, notes=reason)
            return False, reason

    mark_ai_validated(case_id, "research", True, notes=reason or None)
    return True, reason
