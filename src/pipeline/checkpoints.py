"""
Generic human<->AI validation checkpoint, shared by every pipeline step.
One row per (case, step) — see docs/TRACKER.md Phase 21 and
src/db/models.py's StepCheckpoint for the schema/state-machine rationale.

Each step-specific phase (research, characters, script, audio, EDL, ...)
calls these helpers instead of inventing its own override/approval pattern.
Step-specific *validation logic* (what counts as a passing check) lives in
each step's own agent/route — this module only owns the state transitions.
"""
from __future__ import annotations

import uuid
from typing import Optional

from src.db.models import StepCheckpoint
from src.db.session import get_session


def get_checkpoint(case_id: str, step: str) -> Optional[dict]:
    with get_session() as session:
        row = (
            session.query(StepCheckpoint)
            .filter_by(case_id=uuid.UUID(str(case_id)), step=step)
            .first()
        )
        if row is None:
            return None
        return _to_dict(row)


def list_checkpoints(case_id: str) -> dict[str, dict]:
    with get_session() as session:
        rows = session.query(StepCheckpoint).filter_by(case_id=uuid.UUID(str(case_id))).all()
        return {row.step: _to_dict(row) for row in rows}


def _upsert(case_id: str, step: str, **fields) -> dict:
    with get_session() as session:
        row = (
            session.query(StepCheckpoint)
            .filter_by(case_id=uuid.UUID(str(case_id)), step=step)
            .first()
        )
        if row is None:
            row = StepCheckpoint(case_id=uuid.UUID(str(case_id)), step=step)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        session.flush()
        return _to_dict(row)


def mark_ai_generated(case_id: str, step: str, notes: Optional[str] = None) -> dict:
    return _upsert(case_id, step, status="ai_generated", edited_by="ai", validation_notes=notes)


def mark_human_edited(case_id: str, step: str, notes: Optional[str] = None) -> dict:
    return _upsert(case_id, step, status="human_edited", edited_by="human", validation_notes=notes)


def mark_ai_validated(case_id: str, step: str, passed: bool, notes: Optional[str] = None) -> dict:
    return _upsert(
        case_id, step,
        status="ai_validated" if passed else "ai_flagged",
        validation_notes=notes,
    )


def mark_human_approved(case_id: str, step: str) -> dict:
    return _upsert(case_id, step, status="human_approved", edited_by="human", validation_notes=None)


def mark_human_rejected(case_id: str, step: str, notes: Optional[str] = None) -> dict:
    return _upsert(case_id, step, status="human_rejected", edited_by="human", validation_notes=notes)


def is_approved(case_id: str, step: str) -> bool:
    cp = get_checkpoint(case_id, step)
    return bool(cp and cp["status"] == "human_approved")


def _to_dict(row: StepCheckpoint) -> dict:
    return {
        "step": row.step,
        "status": row.status,
        "edited_by": row.edited_by,
        "validation_notes": row.validation_notes,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
