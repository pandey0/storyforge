from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/{slug}/stream")
async def log_stream(slug: str):
    """
    SSE stream — streams new lines from data/cases/{slug}/logs/pipeline.log.
    Starts from end-of-file so only new lines are sent.
    Compatible with the browser EventSource API.
    """
    log_path = Path(f"data/cases/{slug}/logs/pipeline.log")

    async def generate():
        # Initial keep-alive comment
        yield ": keep-alive\n\n"

        # Start at end of file so we only send new lines
        pos = 0
        if log_path.exists():
            pos = log_path.stat().st_size

        while True:
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                        fh.seek(pos)
                        new = fh.read()
                        if new:
                            pos = fh.tell()
                            for line in new.splitlines():
                                stripped = line.strip()
                                if stripped:
                                    # SSE data must not contain raw newlines inside a field
                                    safe = stripped.replace("\n", " ")
                                    yield f"data: {safe}\n\n"
                except OSError:
                    pass

            await asyncio.sleep(0.5)
            # Heartbeat ping to keep connection alive through proxies
            yield ": ping\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{slug}/tail")
async def log_tail(slug: str, lines: int = 100):
    """Return the last N lines of pipeline.log as JSON."""
    log_path = Path(f"data/cases/{slug}/logs/pipeline.log")

    if not log_path.exists():
        return {"lines": [], "path": str(log_path), "exists": False}

    def _read_tail() -> list[str]:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        return all_lines[-lines:] if len(all_lines) > lines else all_lines

    tail = await asyncio.to_thread(_read_tail)
    return {"lines": tail, "path": str(log_path), "exists": True, "total_returned": len(tail)}
