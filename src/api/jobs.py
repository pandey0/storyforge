from __future__ import annotations

import uuid
from datetime import datetime
from threading import Lock
from typing import Optional

JOBS: dict[str, dict] = {}  # keyed by slug; each value is the job dict
_lock = Lock()

# Keep at most this many finished jobs in memory
_MAX_FINISHED = 10


def start_job(slug: str, step: str) -> str:
    """Creates a job entry for *slug*, returns the new job_id (UUID string)."""
    job_id = str(uuid.uuid4())
    entry = {
        "job_id": job_id,
        "slug": slug,
        "step": step,
        "status": "running",
        "progress": 0,
        "error": None,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }
    with _lock:
        JOBS[slug] = entry
    return job_id


def update_job(slug: str, status: str, progress: Optional[int] = None, error: Optional[str] = None) -> None:
    """Update status / progress on a running job.  No-op if slug unknown."""
    with _lock:
        job = JOBS.get(slug)
        if job is None:
            return
        job["status"] = status
        if progress is not None:
            job["progress"] = progress
        if error is not None:
            job["error"] = error


def finish_job(slug: str, status: str = "done", error: Optional[str] = None) -> None:
    """Mark job complete (or failed).  Keeps entry in JOBS for history."""
    with _lock:
        job = JOBS.get(slug)
        if job is None:
            return
        job["status"] = status
        job["finished_at"] = datetime.utcnow().isoformat()
        if error is not None:
            job["error"] = error
        if progress := job.get("progress"):
            # Mark complete progress on success
            if status == "done":
                job["progress"] = 100

        # Prune old finished jobs (keep last _MAX_FINISHED finished entries)
        finished = [
            (k, v) for k, v in JOBS.items()
            if v.get("finished_at") and k != slug
        ]
        if len(finished) > _MAX_FINISHED:
            finished.sort(key=lambda kv: kv[1]["finished_at"])
            for old_slug, _ in finished[: len(finished) - _MAX_FINISHED]:
                del JOBS[old_slug]


def is_running(slug: str) -> bool:
    """Return True if a job for *slug* is currently in running state."""
    with _lock:
        job = JOBS.get(slug)
        return job is not None and job.get("status") == "running"


def get_job(slug: str) -> Optional[dict]:
    """Return the current job dict for *slug*, or None if not found."""
    with _lock:
        job = JOBS.get(slug)
        return dict(job) if job else None


def get_all_jobs() -> list[dict]:
    """Return all jobs — running ones plus the last _MAX_FINISHED finished ones."""
    with _lock:
        all_entries = list(JOBS.values())

    running = [j for j in all_entries if not j.get("finished_at")]
    finished = sorted(
        [j for j in all_entries if j.get("finished_at")],
        key=lambda j: j["finished_at"],
        reverse=True,
    )[:_MAX_FINISHED]
    return running + finished
