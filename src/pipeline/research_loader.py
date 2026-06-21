"""
Shared research.json loader, mirroring scripts.py's script_manual.md
priority pattern: a human-edited override file always wins over the
AI-generated artifact when one exists.

Every agent that consumes case research (case_research_agent.py writes the
AI version, script_writer_agent.py / episode_planner_agent.py /
shorts_script_agent.py / character_agent.py / publish_agent.py all read it)
should call load_research(slug) instead of reading
data/cases/{slug}/research.json directly — that's the only way a manual
edit saved via PUT /api/research/{slug} actually takes effect everywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def research_manual_path(slug: str) -> Path:
    return Path(f"data/cases/{slug}/research_manual.json")


def research_ai_path(slug: str) -> Path:
    return Path(f"data/cases/{slug}/research.json")


def load_research(slug: str) -> dict:
    """
    Return the best available research for *slug*.
    Priority: research_manual.json > research.json.
    Raises ValueError if neither file exists or the active one isn't valid JSON.
    """
    manual = research_manual_path(slug)
    if manual.exists():
        try:
            return json.loads(manual.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"research_manual.json for case '{slug}' is not valid JSON: {exc}"
            ) from exc

    ai_path = research_ai_path(slug)
    if ai_path.exists():
        try:
            return json.loads(ai_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"research.json for case '{slug}' is not valid JSON: {exc}"
            ) from exc

    raise ValueError(
        f"No research found for case '{slug}'. "
        f"Expected one of: {manual.resolve()}, {ai_path.resolve()}"
    )


def load_research_source(slug: str) -> Optional[str]:
    """Return 'manual', 'ai', or None — which file load_research would use."""
    if research_manual_path(slug).exists():
        return "manual"
    if research_ai_path(slug).exists():
        return "ai"
    return None
