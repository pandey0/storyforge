from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.models import Case, Script
from src.db.session import get_session

router = APIRouter(prefix="/scripts", tags=["scripts"])


class ScriptSaveBody(BaseModel):
    text: str


def _count_words(text: str) -> int:
    return len(text.split())


def _script_row_to_dict(row: Script) -> dict:
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "version": row.version,
        "word_count": row.word_count,
        "duration_est_min": row.duration_est_min,
        "status": row.status,
        "qa_notes": row.qa_notes,
        "qa_attempts": row.qa_attempts,
        "approved_by": row.approved_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


@router.get("/{slug}")
async def get_script(slug: str):
    """
    Return the best available script for this case.
    Priority: script_manual.md > script_draft.md > latest DB row.
    Returns the source name, text, and word count.
    """
    def _fetch():
        base = Path(f"data/cases/{slug}")

        manual = base / "script_manual.md"
        if manual.exists():
            text = manual.read_text(encoding="utf-8")
            return {"text": text, "source": "manual", "word_count": _count_words(text)}

        draft = base / "script_draft.md"
        if draft.exists():
            text = draft.read_text(encoding="utf-8")
            return {"text": text, "source": "draft", "word_count": _count_words(text)}

        # Fall back to DB
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None
            row = (
                session.query(Script)
                .filter(Script.case_id == case.id)
                .order_by(Script.version.desc())
                .first()
            )
            if row and row.script_text:
                return {
                    "text": row.script_text,
                    "source": "db",
                    "word_count": row.word_count or _count_words(row.script_text),
                }

        return None

    data = await asyncio.to_thread(_fetch)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No script found for case '{slug}'")
    return data


@router.put("/{slug}")
async def save_script(slug: str, body: ScriptSaveBody):
    """
    Save text to script_manual.md — this will take priority over AI-generated drafts.
    Also inserts/updates the Script DB row.
    """
    def _save():
        # Verify case exists
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "not_found"

        # Write file
        base = Path(f"data/cases/{slug}")
        base.mkdir(parents=True, exist_ok=True)
        manual_path = base / "script_manual.md"
        manual_path.write_text(body.text, encoding="utf-8")

        wc = _count_words(body.text)
        duration_est = round(wc / 125, 2)

        # Upsert DB row
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            existing = (
                session.query(Script)
                .filter(Script.case_id == case.id)
                .order_by(Script.version.desc())
                .first()
            )
            if existing:
                existing.script_text = body.text
                existing.word_count = wc
                existing.duration_est_min = duration_est
                existing.status = "manual"
            else:
                row = Script(
                    case_id=case.id,
                    version=1,
                    script_text=body.text,
                    word_count=wc,
                    duration_est_min=duration_est,
                    status="manual",
                )
                session.add(row)
            session.flush()

        return {
            "saved": True,
            "path": str(manual_path),
            "word_count": wc,
            "duration_est_min": duration_est,
        }, None

    result, err = await asyncio.to_thread(_save)
    if err == "not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    return result


@router.delete("/{slug}/manual", status_code=200)
async def delete_manual_script(slug: str):
    """Remove the manual script override so the AI draft is used instead."""
    def _delete():
        manual = Path(f"data/cases/{slug}/script_manual.md")
        if not manual.exists():
            return False
        manual.unlink()
        return True

    deleted = await asyncio.to_thread(_delete)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No manual script found for '{slug}'")
    return {"deleted": True, "path": f"data/cases/{slug}/script_manual.md"}


@router.get("/{slug}/versions")
async def get_script_versions(slug: str):
    """List all Script DB rows for this case, newest first."""
    def _fetch():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None
            rows = (
                session.query(Script)
                .filter(Script.case_id == case.id)
                .order_by(Script.version.desc())
                .all()
            )
            return [_script_row_to_dict(r) for r in rows]

    data = await asyncio.to_thread(_fetch)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    return data
