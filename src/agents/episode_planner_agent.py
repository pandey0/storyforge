from __future__ import annotations

import json
import os
import re
from pathlib import Path

from loguru import logger

from src.db.channel_profile import get_profile_for_case
from src.pipeline.state import CaseState

_REQUIRED_CARD_FIELDS = ("slug", "label", "hook_text", "angle", "broll_query", "role_hint", "cta")


def _load_research(slug: str) -> dict:
    path = Path(f"data/cases/{slug}/research.json")
    if not path.exists():
        raise ValueError(
            f"research.json not found for case '{slug}'. Expected path: {path.resolve()}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json_array(text: str) -> list[dict]:
    """Parse a JSON array out of a Gemini response, tolerating markdown fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of episode cards, got: {type(data)}")
    return data


def _validate_cards(cards: list[dict]) -> list[dict]:
    if not cards:
        raise ValueError("Planner returned zero episode cards")
    seen_slugs: set[str] = set()
    for i, card in enumerate(cards):
        missing = [f for f in _REQUIRED_CARD_FIELDS if f not in card]
        if missing:
            raise ValueError(f"Episode card {i} missing fields: {missing}")
        if card["slug"] in seen_slugs:
            raise ValueError(f"Duplicate episode slug in plan: {card['slug']}")
        seen_slugs.add(card["slug"])
    return cards


class EpisodePlannerAgent:
    """
    Decides shorts episode count + identity from a case's actual research —
    no fixed topic menu. See docs/TRACKER.md Phase 20.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash")

    def run(self, state: CaseState) -> CaseState:
        slug = state.slug
        logger.info(f"EpisodePlannerAgent starting | case={slug}")

        profile = get_profile_for_case(slug)
        research = _load_research(slug)

        if not profile.shorts_planner_prompt:
            raise ValueError(
                f"Profile '{profile.slug}' has no shorts_planner_prompt configured"
            )
        prompt = profile.shorts_planner_prompt.format(language=profile.language)
        prompt += f"\n\nCASE RESEARCH (JSON):\n{json.dumps(research, ensure_ascii=False, indent=2)}"

        import google.generativeai as genai
        response = self._model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=4000,
            ),
        )
        cards = _validate_cards(_extract_json_array(response.text))

        out_path = Path(f"data/cases/{slug}/shorts_plan.json")
        out_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"EpisodePlannerAgent done | {len(cards)} episodes planned | case={slug} | path={out_path}")

        state.shorts_plan_path = str(out_path)
        return state
