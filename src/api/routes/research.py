from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.models import Case
from src.db.session import get_session
from src.pipeline.checkpoints import mark_human_edited
from src.pipeline.research_loader import research_ai_path, research_manual_path

router = APIRouter(prefix="/research", tags=["research"])

_REQUIRED_KEYS = ("case_name", "summary", "sources")


class ResearchSaveBody(BaseModel):
    data: dict


def _case_id(slug: str) -> str:
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
        return str(case.id)


@router.get("/{slug}")
async def get_research(slug: str):
    """
    Return the best available research for this case.
    Priority: research_manual.json > research.json.
    """
    def _fetch():
        manual = research_manual_path(slug)
        if manual.exists():
            data = json.loads(manual.read_text(encoding="utf-8"))
            return {"data": data, "source": "manual"}

        ai_path = research_ai_path(slug)
        if ai_path.exists():
            data = json.loads(ai_path.read_text(encoding="utf-8"))
            return {"data": data, "source": "ai"}

        return None

    result = await asyncio.to_thread(_fetch)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No research found for case '{slug}'")
    return result


@router.put("/{slug}")
async def save_research(slug: str, body: ResearchSaveBody):
    """
    Save data to research_manual.json — this takes priority over the
    AI-generated research.json. Mirrors scripts.py's script_manual.md pattern.
    """
    data = body.data
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="data must be a JSON object")
    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"data is missing required top-level keys: {missing}",
        )

    case_id = await asyncio.to_thread(_case_id, slug)

    def _save():
        base = Path(f"data/cases/{slug}")
        base.mkdir(parents=True, exist_ok=True)
        manual_path = base / "research_manual.json"
        manual_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(manual_path)

    path = await asyncio.to_thread(_save)
    await asyncio.to_thread(mark_human_edited, case_id, "research", "manual edit via dashboard")

    return {"saved": True, "path": path}


@router.delete("/{slug}", status_code=200)
async def delete_manual_research(slug: str):
    """Remove the manual research override so the AI-generated version is used instead."""
    def _delete():
        manual = research_manual_path(slug)
        if not manual.exists():
            return False
        manual.unlink()
        return True

    deleted = await asyncio.to_thread(_delete)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No manual research override found for '{slug}'")
    return {"deleted": True, "path": str(research_manual_path(slug))}


@router.post("/{slug}/validate")
async def validate_research_route(slug: str):
    from src.agents.research_validator import validate_research

    case_id = await asyncio.to_thread(_case_id, slug)

    def _run():
        return validate_research(case_id, slug)

    passed, notes = await asyncio.to_thread(_run)
    return {"passed": passed, "notes": notes}
