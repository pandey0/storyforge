from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    case_slug: Optional[str] = None
    history: list[dict] = []


class ExecuteRequest(BaseModel):
    action_id: str


# ---------------------------------------------------------------------------
# Lazy agent singleton (avoids importing google.generativeai at startup)
# ---------------------------------------------------------------------------

_agent = None
_agent_lock = None


def _get_agent_instance():
    """Return a lazily-constructed PipelineAgent singleton."""
    global _agent, _agent_lock
    import threading
    if _agent_lock is None:
        _agent_lock = threading.Lock()
    with _agent_lock:
        if _agent is None:
            from dotenv import load_dotenv
            load_dotenv()
            from src.api.agent.core import PipelineAgent
            _agent = PipelineAgent()
    return _agent


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat")
async def agent_chat(body: ChatRequest):
    """
    Send a message to the conversational pipeline agent.
    The agent has real Gemini tool-calling capability:
    it can inspect cases, read logs, trigger pipeline steps, etc.
    """
    def _run():
        agent = _get_agent_instance()
        return agent.chat(
            message=body.message,
            case_slug=body.case_slug,
            history=body.history,
        )

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "reply": result["reply"],
        "tool_calls": result.get("tool_calls", []),
        "action_cards": result.get("action_cards", []),
    }


@router.get("/status")
async def agent_status():
    """
    Return pending action cards (awaiting user approval) and recent notifications.
    These are stored in the agent core module's in-memory stores.
    """
    def _fetch():
        from src.api.agent.core import PENDING_ACTIONS, NOTIFICATIONS
        return {
            "notifications": list(NOTIFICATIONS[:50]),
            "pending_actions": list(PENDING_ACTIONS.values()),
        }

    return await asyncio.to_thread(_fetch)


@router.post("/execute")
async def execute_action(body: ExecuteRequest):
    """
    Execute a pending action card that was proposed by the agent.
    The card is removed from the pending store once dispatched.
    """
    def _run():
        agent = _get_agent_instance()
        return agent.execute_action(body.action_id)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("error") == "Action not found":
        raise HTTPException(status_code=404, detail=f"Action '{body.action_id}' not found or already executed")

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.post("/monitor")
async def trigger_monitor():
    """
    Run a manual monitoring sweep — checks for failed cases,
    updates the notifications list, and optionally triggers the RSS scraper.
    """
    import threading

    def _run_monitor():
        from dotenv import load_dotenv
        load_dotenv()

        # Agent monitor sweep (check for failures, populate notifications)
        try:
            agent = _get_agent_instance()
            agent.monitor()
        except Exception:
            pass

        # Optional: trigger RSS scraper if available
        try:
            from src.scrapers.rss_monitor import RSSMonitor
            RSSMonitor().run()
        except Exception:
            pass

    t = threading.Thread(target=_run_monitor, daemon=True)
    t.start()

    return {"started": True, "message": "Monitor sweep started in background"}
