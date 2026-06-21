from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from src.db.channel_profile import get_profile_for_case
from src.db.models import ChannelProfile
from src.pipeline.research_loader import load_research as _load_research_file
from src.pipeline.state import CaseState

# Minimum words of research content required to bother writing an episode at all.
_MIN_RESEARCH_WORDS = 40


def _count_words(text: str) -> int:
    return len(text.split())


def _load_research(slug: str) -> dict:
    """Load and return the best available research (manual override > AI) for *slug*.

    Raises ValueError with a clear message if neither file is present or valid.
    """
    data = _load_research_file(slug)
    logger.info(f"Loaded research | case={slug} | keys={list(data.keys())}")
    return data


def _load_plan(slug: str) -> list[dict]:
    """Load shorts_plan.json — the dynamically-planned episode cards for *slug*.

    Raises ValueError if no plan exists; the planner step must run first.
    """
    path = Path(f"data/cases/{slug}/shorts_plan.json")
    if not path.exists():
        raise ValueError(
            f"shorts_plan.json not found for case '{slug}' — run the Episode "
            f"Plan step first. Expected path: {path.resolve()}"
        )
    cards = json.loads(path.read_text(encoding="utf-8"))
    if not cards:
        raise ValueError(f"shorts_plan.json for case '{slug}' is empty")
    return cards


def _research_context(research: dict) -> str:
    """Full research dump as plain text — the planner already decided each
    episode's specific angle, so the writer just needs everything available
    and the card's `angle` to focus itself; no per-topic field mapping.

    Matches case_research_agent.py's actual output shape: a `summary` dict
    (subject/year/location/key_entities/key_facts/outcome — generic fields,
    not crime-specific) plus `sources` (indian_kanoon/news_archive/wikipedia/
    cbi_press lists/dicts).
    """
    case_name = research.get("case_name", "Unknown Case")
    summary = research.get("summary") or {}
    sources = research.get("sources") or {}

    parts = [f"CASE: {case_name}"]

    if isinstance(summary, dict):
        lines = []
        if summary.get("subject"):
            lines.append(f"Subject: {summary['subject']}")
        if summary.get("year"):
            lines.append(f"Year: {summary['year']}")
        if summary.get("location"):
            lines.append(f"Location: {summary['location']}")
        if summary.get("key_entities"):
            lines.append(
                "Key people/entities:\n"
                + "\n".join(f"- {e.get('name')} ({e.get('role')})" for e in summary["key_entities"])
            )
        if summary.get("key_facts"):
            lines.append("Key facts:\n" + "\n".join(f"- {f}" for f in summary["key_facts"]))
        if summary.get("outcome"):
            lines.append(f"Outcome: {summary['outcome']}")
        if lines:
            parts.append("SUMMARY:\n" + "\n".join(lines))
    elif isinstance(summary, str) and summary:
        parts.append(f"SUMMARY:\n{summary}")

    wiki = sources.get("wikipedia") or {}
    wiki_text = wiki.get("extract_full") or wiki.get("extract_summary")
    if wiki_text:
        parts.append(f"WIKIPEDIA:\n{wiki_text}")

    news = sources.get("news_archive") or []
    if news:
        lines = [f"- {a.get('title','')}: {a.get('content','')}" for a in news]
        parts.append("NEWS ARCHIVE:\n" + "\n".join(lines))

    judgments = sources.get("indian_kanoon") or []
    if judgments:
        lines = [
            f"- {d.get('title') or d.get('headline','')} ({d.get('court','')}, {d.get('date','')})"
            for d in judgments
        ]
        parts.append("COURT JUDGMENTS:\n" + "\n".join(lines))

    cbi = sources.get("cbi_press") or []
    if cbi:
        parts.append("CBI PRESS:\n" + json.dumps(cbi, ensure_ascii=False))

    return "\n\n".join(parts)


def _has_enough_research(research: dict) -> bool:
    return _count_words(_research_context(research)) >= _MIN_RESEARCH_WORDS


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ShortsScriptAgent:
    def __init__(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash")

    def run(self, state: CaseState) -> CaseState:
        logger.info(f"ShortsScriptAgent starting | case={state.slug}")

        profile = get_profile_for_case(state.slug)
        research = _load_research(state.slug)
        cards = _load_plan(state.slug)
        case_name = research.get("case_name", state.slug)

        if not _has_enough_research(research):
            raise ValueError(
                f"Insufficient research data for case '{state.slug}' "
                f"(< {_MIN_RESEARCH_WORDS} words) — cannot write episodes"
            )
        context = _research_context(research)

        shorts_dir = Path(f"data/cases/{state.slug}/shorts")
        shorts_dir.mkdir(parents=True, exist_ok=True)

        episode_paths: list[str] = []
        for ep_num, card in enumerate(cards, start=1):
            logger.info(f"Writing episode | slug={card['slug']} | ep={ep_num:02d}")
            script = self._write_episode(profile, case_name, card, context)

            filename = f"ep{ep_num:02d}_{card['slug']}.md"
            out_path = shorts_dir / filename
            out_path.write_text(script, encoding="utf-8")
            logger.info(f"Saved episode | path={out_path} | words={_count_words(script)}")

            episode_paths.append(str(out_path))

        state.shorts_episode_paths = episode_paths
        logger.info(
            f"ShortsScriptAgent done | {len(episode_paths)} episodes saved | case={state.slug}"
        )
        return state

    def run_single(self, state: CaseState, episode_slug: str) -> CaseState:
        """Generate (or regenerate) exactly one episode, leaving the others untouched."""
        profile = get_profile_for_case(state.slug)
        cards = _load_plan(state.slug)
        card = next((c for c in cards if c["slug"] == episode_slug), None)
        if card is None:
            raise ValueError(f"Unknown episode slug (not in shorts_plan.json): {episode_slug}")

        research = _load_research(state.slug)
        case_name = research.get("case_name", state.slug)

        shorts_dir = Path(f"data/cases/{state.slug}/shorts")
        shorts_dir.mkdir(parents=True, exist_ok=True)

        if not _has_enough_research(research):
            raise ValueError(
                f"Insufficient research data for case '{state.slug}' "
                f"(< {_MIN_RESEARCH_WORDS} words)"
            )
        context = _research_context(research)

        logger.info(f"Writing single episode | slug={episode_slug} | case={state.slug}")
        script = self._write_episode(profile, case_name, card, context)

        # Reuse existing ep-number for this slug if it already has a file (regeneration);
        # otherwise assign the next free slot so numbering stays sequential with the plan order.
        existing = sorted(shorts_dir.glob(f"ep*_{episode_slug}.md"))
        if existing:
            out_path = existing[0]
        else:
            plan_index = next(i for i, c in enumerate(cards, start=1) if c["slug"] == episode_slug)
            out_path = shorts_dir / f"ep{plan_index:02d}_{episode_slug}.md"

        out_path.write_text(script, encoding="utf-8")
        logger.info(f"Saved episode | path={out_path} | words={_count_words(script)}")

        state.shorts_episode_paths = [str(out_path)]
        return state

    def _write_episode(
        self,
        profile: ChannelProfile,
        case_name: str,
        card: dict,
        research_context: str,
    ) -> str:
        import google.generativeai as genai

        prompt = profile.shorts_episode_prompt_template.format(
            topic_label=card["label"],
            case_name=case_name,
            topic_context=research_context,
            topic_guidance=card["angle"],
            topic_cta=card["cta"],
        )
        response = self._model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                # gemini-2.5-flash spends an uncontrollable chunk of this budget on
                # internal "thinking" before any visible text — this SDK (0.7.2)
                # predates thinking_config, so there's no way to disable it. 600
                # was sized for a non-thinking model and left ~0 tokens for the
                # actual script, truncating to a few words. 3000 leaves enough
                # headroom after thinking for the real 120-180 word output.
                max_output_tokens=3000,
            ),
        )
        return response.text.strip()
