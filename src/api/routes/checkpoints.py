from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])


class RejectBody(BaseModel):
    notes: str = ""


def _case_id(slug: str) -> str:
    from src.db.models import Case
    from src.db.session import get_session

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
        return str(case.id)


@router.get("/{slug}")
async def get_all_checkpoints(slug: str):
    import asyncio
    from src.pipeline.checkpoints import list_checkpoints

    def _fetch():
        return list_checkpoints(_case_id(slug))

    return await asyncio.to_thread(_fetch)


@router.get("/{slug}/{step}")
async def get_one_checkpoint(slug: str, step: str):
    import asyncio
    from src.pipeline.checkpoints import get_checkpoint

    def _fetch():
        cp = get_checkpoint(_case_id(slug), step)
        return cp or {"step": step, "status": None, "edited_by": None, "validation_notes": None, "updated_at": None}

    return await asyncio.to_thread(_fetch)


@router.post("/{slug}/{step}/approve")
async def approve_checkpoint(slug: str, step: str):
    import asyncio
    from src.pipeline.checkpoints import mark_human_approved

    def _run():
        return mark_human_approved(_case_id(slug), step)

    return await asyncio.to_thread(_run)


@router.post("/{slug}/{step}/reject")
async def reject_checkpoint(slug: str, step: str, body: RejectBody):
    import asyncio
    from src.pipeline.checkpoints import mark_human_rejected

    def _run():
        return mark_human_rejected(_case_id(slug), step, notes=body.notes or None)

    return await asyncio.to_thread(_run)
