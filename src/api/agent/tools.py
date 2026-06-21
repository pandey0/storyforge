import json
import os
import threading
from pathlib import Path
from datetime import datetime, timezone
from src.db.session import get_session
from src.db.models import Case, Script, Video, CaseCharacter, PipelineLog
import uuid as _uuid

PROJECT_ROOT = Path("/home/dell/COurse/cash/indiancrimes")


def get_all_cases() -> list[dict]:
    """Get all cases with status, file presence, last pipeline log line."""
    with get_session() as s:
        cases = s.query(Case).order_by(Case.updated_at.desc()).all()
        result = []
        for c in cases:
            log_tail = ""
            log_path = PROJECT_ROOT / f"data/cases/{c.slug}/logs/pipeline.log"
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8").strip().splitlines()
                log_tail = lines[-1] if lines else ""
            result.append({
                "slug": c.slug,
                "name": c.name,
                "status": c.status,
                "updated_at": str(c.updated_at) if c.updated_at else None,
                "notes": c.notes,
                "last_log": log_tail,
            })
        return result


def get_case_detail(slug: str) -> dict:
    """Full case detail with script info, video info, recent logs."""
    with get_session() as s:
        c = s.query(Case).filter_by(slug=slug).first()
        if not c:
            return {"error": f"Case not found: {slug}"}
        scripts = s.query(Script).filter_by(case_id=c.id).order_by(Script.version.desc()).all()
        videos = s.query(Video).filter_by(case_id=c.id).all()
        result = {
            "slug": c.slug,
            "name": c.name,
            "status": c.status,
            "subject_name": c.subject_name,
            "location": c.location,
            "year": c.year_of_crime,
            "notes": c.notes,
            "scripts": [
                {
                    "version": sc.version,
                    "status": sc.status,
                    "qa_notes": sc.qa_notes,
                    "word_count": sc.word_count,
                }
                for sc in scripts
            ],
            "videos": [
                {
                    "render_status": v.render_status,
                    "duration_sec": v.duration_sec,
                }
                for v in videos
            ],
        }
        return result


def get_pipeline_logs(slug: str, step: str = "pipeline", lines: int = 100) -> str:
    """Get last N lines of pipeline log for a case."""
    log_path = PROJECT_ROOT / f"data/cases/{slug}/logs/{step}.log"
    if not log_path.exists():
        return f"No log file found at {log_path}"
    all_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    return "\n".join(all_lines[-lines:])


def get_script(slug: str) -> str:
    """Get current script text (manual override if exists)."""
    for p in [
        PROJECT_ROOT / f"data/cases/{slug}/script_manual.md",
        PROJECT_ROOT / f"data/cases/{slug}/script_draft.md",
    ]:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            return (
                f"[Source: {p.name}]\n\n"
                + text[:4000]
                + ("...(truncated)" if len(text) > 4000 else "")
            )
    return "No script found"


def get_file_tree(slug: str) -> dict:
    """Check which files exist for a case."""
    base = PROJECT_ROOT / f"data/cases/{slug}"

    def check(rel: str) -> dict:
        p = base / rel
        if p.exists():
            return {"exists": True, "size_mb": round(p.stat().st_size / (1024 * 1024), 2)}
        return {"exists": False}

    chars_dir = base / "characters"
    char_count = len(list(chars_dir.glob("*"))) if chars_dir.exists() else 0

    return {
        "research.json": check("research.json"),
        "script_draft.md": check("script_draft.md"),
        "script_manual.md": check("script_manual.md"),
        "voiceover.mp3": check("audio/voiceover.mp3"),
        "word_timings.json": check("audio/word_timings.json"),
        "video_final.mp4": check("output/video_final.mp4"),
        "thumbnail.jpg": check("output/thumbnail.jpg"),
        "characters_count": char_count,
    }


def trigger_pipeline_step(slug: str, step: str) -> dict:
    """Trigger a pipeline step for a case in a background thread."""
    valid_steps = ["research", "script", "tts", "characters", "broll", "assemble", "thumbnail"]
    if step not in valid_steps:
        return {"error": f"Invalid step: {step}. Valid: {valid_steps}"}

    # Import here to avoid circular imports
    try:
        from src.api.jobs import start_job, finish_job, update_job
    except ImportError:
        return {"error": "jobs module not available yet"}

    job_id = start_job(slug, step)

    def run():
        from dotenv import load_dotenv
        load_dotenv()
        try:
            from src.db.session import get_session
            from src.db.models import Case
            from src.pipeline.state import CaseState

            with get_session() as s:
                case = s.query(Case).filter_by(slug=slug).first()
                if not case:
                    finish_job(slug, "failed", f"Case not found: {slug}")
                    return
                state = CaseState.from_db_case(case)
                state.case_id = str(case.id)

            # Set file paths from disk
            for p in [
                f"data/cases/{slug}/script_draft.md",
                f"data/cases/{slug}/script_manual.md",
            ]:
                if Path(p).exists():
                    state.draft_script_path = p
            audio = f"data/cases/{slug}/audio/voiceover.mp3"
            if Path(audio).exists():
                state.audio_path = audio
            timings = f"data/cases/{slug}/audio/word_timings.json"
            if Path(timings).exists():
                state.timings_path = timings
            broll = f"data/cases/{slug}/broll/"
            if Path(broll).exists():
                state.broll_dir = broll

            update_job(slug, "running")

            if step == "research":
                from src.agents.case_research_agent import CaseResearchAgent
                CaseResearchAgent().run(slug)
            elif step == "script":
                from src.agents.script_writer_agent import ScriptWriterAgent
                ScriptWriterAgent().run(state)
            elif step == "tts":
                from src.agents.tts_agent import TTSAgent
                TTSAgent().run(state)
            elif step == "characters":
                from src.agents.character_agent import CharacterAgent
                CharacterAgent().run(state)
            elif step == "broll":
                from src.agents.broll_agent import BRollAgent
                BRollAgent().run(state)
            elif step == "assemble":
                from src.video.assembler import VideoCreator
                VideoCreator().create(state)
            elif step == "thumbnail":
                from src.agents.thumbnail_agent import ThumbnailAgent
                ThumbnailAgent().run(state)

            finish_job(slug, "done")
        except Exception as e:
            finish_job(slug, "failed", str(e))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"job_id": job_id, "slug": slug, "step": step, "message": f"Started {step} for {slug}"}


def read_source_file(relative_path: str) -> str:
    """Read a source file for diagnosis. Only src/ paths allowed."""
    if not relative_path.startswith("src/"):
        return "Error: only src/ paths allowed for security"
    full = PROJECT_ROOT / relative_path
    if not full.exists():
        return f"File not found: {relative_path}"
    text = full.read_text(encoding="utf-8")
    if len(text) > 3000:
        return text[:3000] + f"\n...(truncated, {len(text)} total chars)"
    return text


def propose_script_fix(slug: str, issue: str, fixed_content: str) -> dict:
    """Create an action card proposing a script fix. User must approve."""
    action_id = str(_uuid.uuid4())[:8]
    return {
        "type": "action_card",
        "id": action_id,
        "action_type": "write_script_fix",
        "title": f"Script fix: {issue[:60]}",
        "description": (
            f"Agent proposes writing a fixed script ({len(fixed_content)} chars). "
            "Review and approve to apply."
        ),
        "severity": "warning",
        "requires_approval": True,
        "payload": {"slug": slug, "content": fixed_content, "issue": issue},
    }


def get_recent_errors() -> list[dict]:
    """Get cases with recent errors in pipeline logs."""
    errors = []
    with get_session() as s:
        failed = s.query(Case).filter(Case.status == "failed").all()
        for c in failed:
            log_tail = get_pipeline_logs(c.slug, "pipeline", 20)
            errors.append({
                "slug": c.slug,
                "name": c.name,
                "status": c.status,
                "notes": c.notes,
                "recent_logs": log_tail,
            })
    return errors


def get_all_jobs_tool() -> list[dict]:
    """Get all running and recent background jobs."""
    try:
        from src.api.jobs import get_all_jobs
        return get_all_jobs()
    except ImportError:
        return []
