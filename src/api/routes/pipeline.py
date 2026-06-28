from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.jobs import finish_job, get_all_jobs, get_job, is_running, start_job, update_job
from src.api.log_writer import PipelineLogger
from src.api.cache import invalidate_slug
from src.api.versions import STEP_FILE_MAP

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

def _shorts_plan_slugs(slug: str) -> set[str]:
    """Valid episode slugs for *slug*, read from its dynamic shorts_plan.json.

    Empty set (not an error) if no plan has been generated yet — callers
    treat an empty set as "no constraint" vs. "definitely invalid".
    """
    import json
    plan_path = Path(f"data/cases/{slug}/shorts_plan.json")
    if not plan_path.exists():
        return set()
    try:
        cards = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return {c["slug"] for c in cards if "slug" in c}

# ---------------------------------------------------------------------------
# Status progression map
# ---------------------------------------------------------------------------

_STATUS_PROGRESSION = [
    "queued",
    "research",
    "scripting",
    "human_review",
    "tts",
    "broll",
    "video",
    "thumbnail",
    "ready",
]


def _next_status(current: str) -> Optional[str]:
    try:
        idx = _STATUS_PROGRESSION.index(current)
        if idx + 1 < len(_STATUS_PROGRESSION):
            return _STATUS_PROGRESSION[idx + 1]
    except ValueError:
        pass
    return None


def _prev_status(current: str) -> Optional[str]:
    try:
        idx = _STATUS_PROGRESSION.index(current)
        if idx - 1 >= 0:
            return _STATUS_PROGRESSION[idx - 1]
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------------------
# Helper: build CaseState from DB
# ---------------------------------------------------------------------------


def _build_state(slug: str):
    """Load Case from DB and construct a CaseState with file paths resolved."""
    from src.db.models import Case
    from src.db.session import get_session
    from src.pipeline.state import CaseState

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise ValueError(f"Case not found: {slug}")
        state = CaseState.from_db_case(case)
        state.case_id = str(case.id)

        # Resolve optional file paths
        research_path = Path(f"data/cases/{slug}/research.json")
        if research_path.exists():
            state.research_path = str(research_path)

        for p in [
            f"data/cases/{slug}/script_manual.md",
            f"data/cases/{slug}/script_draft.md",
        ]:
            if Path(p).exists():
                state.draft_script_path = p
                break

        audio = Path(f"data/cases/{slug}/audio/voiceover.mp3")
        if audio.exists():
            state.audio_path = str(audio)

        timings = Path(f"data/cases/{slug}/audio/word_timings.json")
        if timings.exists():
            state.timings_path = str(timings)

        broll = Path(f"data/cases/{slug}/broll/")
        if broll.exists():
            state.broll_dir = str(broll)

        video_path = Path(f"data/cases/{slug}/output/video_final.mp4")
        if video_path.exists():
            state.video_path = str(video_path)

        thumbnail_path = Path(f"data/cases/{slug}/output/thumbnail.jpg")
        if thumbnail_path.exists():
            state.thumbnail_path = str(thumbnail_path)

    return state


def _guard_already_running(slug: str) -> None:
    """Raise 409 if a job is already running for this slug."""
    if is_running(slug):
        raise HTTPException(status_code=409, detail=f"Job already running for '{slug}'")


def _update_case_status(slug: str, status: str) -> None:
    from src.db.models import Case
    from src.db.session import get_session

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case:
            case.status = status


# ---------------------------------------------------------------------------
# Background thread runner factory
# ---------------------------------------------------------------------------


def _run_in_thread(target_fn, slug: str, step: str, log: PipelineLogger) -> None:
    """Wrap agent execution: update_job on error, finish_job on completion."""
    try:
        from dotenv import load_dotenv
        load_dotenv()  # threads don't inherit startup env load
        target_fn()
        finish_job(slug, status="done")
    except Exception as exc:
        log.error(f"FATAL: {exc}")
        finish_job(slug, status="failed", error=str(exc))
        _update_case_status(slug, "failed")
    finally:
        invalidate_slug(slug)  # clear file/case cache so UI sees new artifacts


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ApproveBody(BaseModel):
    pass


class RejectBody(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Research route
# ---------------------------------------------------------------------------


@router.post("/{slug}/research")
async def run_research(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "research")
    log = PipelineLogger(slug, "research")
    log.info(f"Research job started | job_id={job_id}")

    def _run():
        from src.agents.case_research_agent import CaseResearchAgent
        log.info("Running CaseResearchAgent")
        update_job(slug, "running", progress=10)
        agent = CaseResearchAgent()
        agent.run(slug)
        log.info("CaseResearchAgent complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "research", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "Research started in background"}


# ---------------------------------------------------------------------------
# Script route
# ---------------------------------------------------------------------------


@router.post("/{slug}/script")
async def run_script(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "script")
    log = PipelineLogger(slug, "script")
    log.info(f"Script job started | job_id={job_id}")

    def _run():
        from src.agents.script_writer_agent import ScriptWriterAgent
        from src.agents.qa_agent import QAAgent
        from src.pipeline.checkpoints import mark_ai_validated
        log.info("Building CaseState")
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        log.info("Running ScriptWriterAgent")
        update_job(slug, "running", progress=10)
        agent = ScriptWriterAgent()
        agent.run(state)
        log.info("ScriptWriterAgent complete")
        update_job(slug, "running", progress=90)

        # AI-generated content (including AI "fix" reruns triggered by QA notes)
        # needs AI-validation before it's presented to the human for approval —
        # same principle as the auto-revalidate-on-manual-edit path in scripts.py.
        log.info("Running QAAgent on freshly generated script")
        qa_state = _build_state(slug)
        if qa_state.draft_script_path:
            passed, notes = QAAgent().run(qa_state)
            mark_ai_validated(qa_state.case_id, "script", passed, notes=notes)
            log.info(f"QA result: passed={passed} notes={notes}")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "script", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "Script writing started in background"}


# ---------------------------------------------------------------------------
# QA route — synchronous
# ---------------------------------------------------------------------------


@router.post("/{slug}/qa")
async def run_qa(slug: str):
    import asyncio

    from src.db.models import Case
    from src.db.session import get_session

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    log = PipelineLogger(slug, "qa")
    log.info("QA check starting (synchronous)")

    def _run():
        from dotenv import load_dotenv
        load_dotenv()
        from src.agents.qa_agent import QAAgent
        from src.pipeline.checkpoints import mark_ai_validated
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        agent = QAAgent()
        passed, notes = agent.run(state)
        # Manual "Run QA" clicks must update the checkpoint too, not just the
        # auto-triggered QA in scripts.py's save_script — approve_gate's guard
        # checks this checkpoint regardless of which path last ran QA.
        mark_ai_validated(state.case_id, "script", passed, notes=notes)
        return passed, notes

    try:
        passed, notes = await asyncio.to_thread(_run)
    except Exception as exc:
        log.error(str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    log.info(f"QA result: passed={passed} notes={notes}")
    return {"passed": passed, "notes": notes}


# ---------------------------------------------------------------------------
# TTS route
# ---------------------------------------------------------------------------


@router.post("/{slug}/tts")
async def run_tts(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "tts")
    log = PipelineLogger(slug, "tts")
    log.info(f"TTS job started | job_id={job_id}")

    def _run():
        import json
        from pathlib import Path
        from src.agents.tts_agent import TTSAgent
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        from src.db.channel_profile import get_profile_for_case
        # Read per-case TTS config
        cfg_path = Path(f"data/cases/{slug}/configs/tts_config.json")
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        log.info(f"TTS config: {cfg}")
        update_job(slug, "running", progress=5)
        # speed may be "0.92|label" format from select — extract numeric part
        raw_speed = str(cfg.get("speed", "0.92")).split("|")[0]
        profile = get_profile_for_case(slug)
        agent = TTSAgent(
            speaker=cfg.get("voice", None),
            speed=float(raw_speed),
            pitch=float(cfg.get("pitch", 0.0)),
            loudness=float(cfg.get("loudness", 1.0)),
            target_language_code=profile.language,
        )
        agent.run(state)
        log.info("TTSAgent complete")

        from src.agents.audio_validator import validate_audio
        passed, notes = validate_audio(state.case_id, slug, track="longform")
        log.info(f"Audio validation: passed={passed} notes={notes}")

        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "tts", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "TTS started in background"}


# ---------------------------------------------------------------------------
# Characters route
# ---------------------------------------------------------------------------


@router.post("/{slug}/characters")
async def run_characters(slug: str):
    import asyncio

    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "characters")
    log = PipelineLogger(slug, "characters")
    log.info(f"Characters extraction job started | job_id={job_id}")

    def _run():
        from src.agents.character_agent import CharacterAgent
        state = _build_state(slug)
        log.info("Running CharacterAgent")
        update_job(slug, "running", progress=10)
        agent = CharacterAgent()
        agent.run(state)
        log.info("CharacterAgent complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "characters", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "Character extraction started in background"}


# ---------------------------------------------------------------------------
# B-Roll route
# ---------------------------------------------------------------------------


@router.post("/{slug}/broll")
async def run_broll(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "broll")
    log = PipelineLogger(slug, "broll")
    log.info(f"B-Roll job started | job_id={job_id}")

    def _run():
        from src.agents.broll_agent import BRollAgent
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        log.info("Running BRollAgent")
        update_job(slug, "running", progress=5)
        agent = BRollAgent()
        agent.run(state)
        log.info("BRollAgent complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "broll", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "B-Roll fetching started in background"}


# ---------------------------------------------------------------------------
# Shorts Episode Planning route
# ---------------------------------------------------------------------------


@router.post("/{slug}/shorts_plan")
async def run_shorts_plan(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "shorts_plan")
    log = PipelineLogger(slug, "shorts_plan")
    log.info(f"Shorts plan job started | job_id={job_id}")

    def _run():
        from src.agents.episode_planner_agent import EpisodePlannerAgent
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        update_job(slug, "running", progress=10)
        log.info("Running EpisodePlannerAgent")
        state = EpisodePlannerAgent().run(state)
        log.info(f"EpisodePlannerAgent complete | plan={state.shorts_plan_path}")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "shorts_plan", log), daemon=True)
    t.start()
    return {"job_id": job_id, "message": "Episode planning started in background"}


# ---------------------------------------------------------------------------
# Shorts Script route
# ---------------------------------------------------------------------------


@router.post("/{slug}/shorts_script")
async def run_shorts_script(slug: str, topic: Optional[str] = None):
    from src.db.models import Case
    from src.db.session import get_session

    if topic is not None:
        valid = _shorts_plan_slugs(slug)
        if valid and topic not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown episode slug: {topic}")

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "shorts_script")
    log = PipelineLogger(slug, "shorts_script")
    log.info(f"Shorts script job started | job_id={job_id} | topic={topic or 'all'}")

    def _run():
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv()
        from src.agents.shorts_script_agent import ShortsScriptAgent
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        update_job(slug, "running", progress=10)
        if topic:
            log.info(f"Running ShortsScriptAgent for topic={topic}")
            state = ShortsScriptAgent().run_single(state, topic)
        else:
            log.info("Running ShortsScriptAgent for all topics")
            state = ShortsScriptAgent().run(state)
        episode_count = len(state.shorts_episode_paths or [])
        log.info(f"ShortsScriptAgent complete | episodes={episode_count}")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "shorts_script", log), daemon=True)
    t.start()
    return {"job_id": job_id, "message": "Shorts script generation started in background"}


# ---------------------------------------------------------------------------
# Shorts TTS route
# ---------------------------------------------------------------------------


@router.post("/{slug}/shorts_tts")
async def run_shorts_tts(slug: str, topic: Optional[str] = None):
    from src.db.models import Case
    from src.db.session import get_session

    if topic is not None:
        valid = _shorts_plan_slugs(slug)
        if valid and topic not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown episode slug: {topic}")

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "shorts_tts")
    log = PipelineLogger(slug, "shorts_tts")
    log.info(f"Shorts TTS job started | job_id={job_id} | topic={topic or 'all'}")

    def _run():
        import json as _json
        import shutil
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv()
        from src.agents.tts_agent import TTSAgent
        from src.db.channel_profile import get_profile_for_case

        shorts_dir = Path(f"data/cases/{slug}/shorts")
        glob_pattern = f"ep*_{topic}.md" if topic else "*.md"
        md_files = sorted(shorts_dir.glob(glob_pattern)) if shorts_dir.is_dir() else []
        if not md_files:
            raise ValueError("No episode scripts found — run shorts_script first")

        # Read per-case shorts_tts config — previously ignored entirely (TTSAgent()
        # with no args always used hardcoded defaults regardless of operator settings)
        cfg_path = Path(f"data/cases/{slug}/configs/shorts_tts_config.json")
        cfg = _json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        log.info(f"Shorts TTS config: {cfg}")
        raw_speed = str(cfg.get("speed", "0.92")).split("|")[0]
        profile = get_profile_for_case(slug)

        state = _build_state(slug)
        state.shorts_episode_paths = [str(p) for p in md_files]
        log.info(f"Found {len(md_files)} episode script(s)")
        update_job(slug, "running", progress=5)

        for i, md_path in enumerate(md_files):
            stem = md_path.stem
            ep_state = _build_state(slug)
            ep_state.draft_script_path = str(md_path)
            ep_state = TTSAgent(
                speaker=cfg.get("voice", None),
                speed=float(raw_speed),
                pitch=float(cfg.get("pitch", 0.0)),
                loudness=float(cfg.get("loudness", 1.0)),
                target_language_code=profile.language,
            ).run(ep_state)
            # Copy audio
            audio_src = Path(f"data/cases/{slug}/audio/voiceover.mp3")
            if audio_src.exists():
                shutil.copy(str(audio_src), str(shorts_dir / f"{stem}.mp3"))
            # Copy timings
            timings_src = Path(f"data/cases/{slug}/audio/word_timings.json")
            if timings_src.exists():
                shutil.copy(str(timings_src), str(shorts_dir / f"{stem}_timings.json"))
            log.info(f"TTS done for episode {i + 1}/{len(md_files)}: {stem}")

            # episode stem is "ep{NN}_{topic}" — strip the "ep{NN}_" prefix to get topic
            stem_parts = stem.split("_", 1)
            ep_topic = stem_parts[1] if len(stem_parts) == 2 and stem_parts[0].startswith("ep") else stem
            from src.agents.audio_validator import validate_audio
            passed, notes = validate_audio(state.case_id, slug, track="shorts", topic=ep_topic)
            log.info(f"Audio validation [{ep_topic}]: passed={passed} notes={notes}")

            update_job(slug, "running", progress=5 + int(90 * (i + 1) / len(md_files)))

        log.info("Shorts TTS complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "shorts_tts", log), daemon=True)
    t.start()
    return {"job_id": job_id, "message": "Shorts TTS started in background"}


# ---------------------------------------------------------------------------
# Shorts Assemble route
# ---------------------------------------------------------------------------


@router.post("/{slug}/shorts_assemble")
async def run_shorts_assemble(slug: str, topic: Optional[str] = None):
    from src.db.models import Case
    from src.db.session import get_session

    if topic is not None:
        valid = _shorts_plan_slugs(slug)
        if valid and topic not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown episode slug: {topic}")

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "shorts_assemble")
    log = PipelineLogger(slug, "shorts_assemble")
    log.info(f"Shorts assemble job started | job_id={job_id} | topic={topic or 'all'}")

    def _run():
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv()
        from src.agents.shorts_assembler_agent import ShortsAssemblerAgent

        shorts_dir = Path(f"data/cases/{slug}/shorts")
        glob_pattern = f"ep*_{topic}.md" if topic else "*.md"
        md_files = sorted(shorts_dir.glob(glob_pattern)) if shorts_dir.is_dir() else []
        if not md_files:
            raise ValueError("No episode scripts — run shorts_script first")

        mp3_pattern = f"ep*_{topic}.mp3" if topic else "*.mp3"
        mp3_files = list(shorts_dir.glob(mp3_pattern)) if shorts_dir.is_dir() else []
        if not mp3_files:
            raise ValueError("No episode audio — run shorts_tts first")

        state = _build_state(slug)
        state.shorts_episode_paths = [str(p) for p in md_files]
        log.info(f"Assembling {len(md_files)} episode(s)")
        update_job(slug, "running", progress=10)
        state = ShortsAssemblerAgent().assemble(state)
        video_count = len(state.shorts_video_paths or [])
        log.info(f"Shorts assembly complete | videos={video_count}")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "shorts_assemble", log), daemon=True)
    t.start()
    return {"job_id": job_id, "message": "Shorts assembly started in background"}


# ---------------------------------------------------------------------------
# Assemble route — very long running
# ---------------------------------------------------------------------------


@router.post("/{slug}/assemble")
async def run_assemble(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "assemble")
    log = PipelineLogger(slug, "assemble")
    log.info(f"Video assembly job started | job_id={job_id}")

    def _run():
        from src.video.assembler import VideoCreator
        state = _build_state(slug)
        if not state.audio_path:
            raise ValueError("No audio found — run TTS step first")
        log.info("Running VideoCreator")
        update_job(slug, "running", progress=5)
        creator = VideoCreator()
        creator.create(state)
        log.info("VideoCreator complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "assemble", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "Video assembly started in background (may take 30+ minutes)"}


# ---------------------------------------------------------------------------
# Thumbnail route
# ---------------------------------------------------------------------------


@router.post("/{slug}/thumbnail")
async def run_thumbnail(slug: str):
    from src.db.models import Case
    from src.db.session import get_session

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    job_id = start_job(slug, "thumbnail")
    log = PipelineLogger(slug, "thumbnail")
    log.info(f"Thumbnail job started | job_id={job_id}")

    def _run():
        from src.agents.thumbnail_agent import ThumbnailAgent
        state = _build_state(slug)
        log.info("Running ThumbnailAgent")
        update_job(slug, "running", progress=10)
        agent = ThumbnailAgent()
        agent.run(state)
        log.info("ThumbnailAgent complete")
        update_job(slug, "running", progress=100)

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "thumbnail", log), daemon=True)
    t.start()

    return {"job_id": job_id, "message": "Thumbnail generation started in background"}


@router.put("/{slug}/thumbnail/replace")
async def replace_thumbnail(slug: str, file: UploadFile = File(...)):
    """Swap data/cases/{slug}/output/thumbnail.jpg for an operator-supplied
    image — without re-running ThumbnailAgent (no DALL-E call, no Pillow
    text-overlay compose). Mirrors ThumbnailAgent's exact output contract
    (1280x720 JPEG, same DB field updated) so downstream consumers (publish
    pipeline, frontend preview) see no difference from an AI-generated one.
    """
    import io

    from PIL import Image, UnidentifiedImageError

    from src.db.models import Case, Video
    from src.db.session import get_session
    from src.pipeline.checkpoints import mark_human_edited

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Validate it's actually an image — verify() raises on truncated/garbage
    # data. Must reopen after verify() since verify() leaves the file unusable
    # for a subsequent load().
    try:
        Image.open(io.BytesIO(contents)).verify()
        img = Image.open(io.BytesIO(contents))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Uploaded file is not a valid image: {exc}")

    # Match ThumbnailAgent's exact output contract: 1280x720 RGB JPEG, quality 95.
    img = img.convert("RGB").resize((1280, 720), Image.LANCZOS)

    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

        out_dir = Path(f"data/cases/{slug}/output")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "thumbnail.jpg"
        img.save(str(out_path), format="JPEG", quality=95)

        # Mirror ThumbnailAgent.run()'s DB side effects exactly: it sets
        # Video.thumbnail_path on the latest Video row for this case.
        video = (
            session.query(Video)
            .filter(Video.case_id == case.id)
            .order_by(Video.created_at.desc())
            .first()
        )
        if video is not None:
            video.thumbnail_path = str(out_path)

        case_id = str(case.id)

    mark_human_edited(case_id, "thumbnail", notes="thumbnail manually replaced")
    invalidate_slug(slug)

    return {
        "replaced": True,
        "path": str(out_path),
        "width": 1280,
        "height": 720,
    }


# ---------------------------------------------------------------------------
# Run Full Pipeline
# ---------------------------------------------------------------------------

LONGFORM_STEPS = ["research", "characters", "script", "qa", "tts", "broll", "assemble", "thumbnail"]
SHORTS_STEPS = ["research", "characters", "shorts_plan", "shorts_script", "shorts_tts", "shorts_assemble"]


def _run_step_core(slug: str, step: str, log: PipelineLogger) -> None:
    """Execute a single pipeline step's agent logic without job lifecycle management.

    Called sequentially by run_full_pipeline. Each branch mirrors the inner _run()
    closure of its individual route handler — same agents, same state, same side
    effects — but without start_job/finish_job calls so the outer run_full job
    stays in control of the lifecycle.
    """
    import json
    from pathlib import Path

    if step == "research":
        from src.agents.case_research_agent import CaseResearchAgent
        log.info("CaseResearchAgent starting")
        CaseResearchAgent().run(slug)

    elif step == "characters":
        from src.agents.character_agent import CharacterAgent
        state = _build_state(slug)
        log.info("CharacterAgent starting")
        CharacterAgent().run(state)

    elif step == "script":
        from src.agents.script_writer_agent import ScriptWriterAgent
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        log.info("ScriptWriterAgent starting")
        ScriptWriterAgent().run(state)

    elif step == "qa":
        from src.agents.qa_agent import QAAgent
        from src.pipeline.checkpoints import mark_ai_validated
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        log.info("QAAgent starting")
        passed, notes = QAAgent().run(state)
        mark_ai_validated(state.case_id, "script", passed, notes=notes)
        log.info(f"QA result: passed={passed} notes={notes}")

    elif step == "tts":
        from src.agents.tts_agent import TTSAgent
        from src.db.channel_profile import get_profile_for_case
        from src.agents.audio_validator import validate_audio
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        cfg_path = Path(f"data/cases/{slug}/configs/tts_config.json")
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        raw_speed = str(cfg.get("speed", "0.92")).split("|")[0]
        profile = get_profile_for_case(slug)
        log.info("TTSAgent starting")
        TTSAgent(
            speaker=cfg.get("voice", None),
            speed=float(raw_speed),
            pitch=float(cfg.get("pitch", 0.0)),
            loudness=float(cfg.get("loudness", 1.0)),
            target_language_code=profile.language,
        ).run(state)
        passed, notes = validate_audio(state.case_id, slug, track="longform")
        log.info(f"Audio validation: passed={passed}")

    elif step == "broll":
        from src.agents.broll_agent import BRollAgent
        state = _build_state(slug)
        if not state.draft_script_path:
            raise ValueError("No script found — run script step first")
        log.info("BRollAgent starting")
        BRollAgent().run(state)

    elif step == "assemble":
        from src.video.assembler import VideoCreator
        state = _build_state(slug)
        if not state.audio_path:
            raise ValueError("No audio found — run TTS step first")
        log.info("VideoCreator starting")
        VideoCreator().create(state)

    elif step == "thumbnail":
        from src.agents.thumbnail_agent import ThumbnailAgent
        state = _build_state(slug)
        log.info("ThumbnailAgent starting")
        ThumbnailAgent().run(state)

    elif step == "shorts_plan":
        from src.agents.episode_planner_agent import EpisodePlannerAgent
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        log.info("EpisodePlannerAgent starting")
        EpisodePlannerAgent().run(state)

    elif step == "shorts_script":
        from src.agents.shorts_script_agent import ShortsScriptAgent
        state = _build_state(slug)
        if not state.research_path:
            raise ValueError("research.json not found — run research step first")
        log.info("ShortsScriptAgent starting (all topics)")
        ShortsScriptAgent().run(state)

    elif step == "shorts_tts":
        import shutil
        from src.agents.tts_agent import TTSAgent
        from src.db.channel_profile import get_profile_for_case
        from src.agents.audio_validator import validate_audio
        shorts_dir = Path(f"data/cases/{slug}/shorts")
        md_files = sorted(shorts_dir.glob("*.md")) if shorts_dir.is_dir() else []
        if not md_files:
            raise ValueError("No episode scripts found — run shorts_script first")
        cfg_path = Path(f"data/cases/{slug}/configs/shorts_tts_config.json")
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        raw_speed = str(cfg.get("speed", "0.92")).split("|")[0]
        profile = get_profile_for_case(slug)
        state = _build_state(slug)
        for i, md_path in enumerate(md_files):
            stem = md_path.stem
            ep_state = _build_state(slug)
            ep_state.draft_script_path = str(md_path)
            ep_state = TTSAgent(
                speaker=cfg.get("voice", None),
                speed=float(raw_speed),
                pitch=float(cfg.get("pitch", 0.0)),
                loudness=float(cfg.get("loudness", 1.0)),
                target_language_code=profile.language,
            ).run(ep_state)
            audio_src = Path(f"data/cases/{slug}/audio/voiceover.mp3")
            if audio_src.exists():
                shutil.copy(str(audio_src), str(shorts_dir / f"{stem}.mp3"))
            timings_src = Path(f"data/cases/{slug}/audio/word_timings.json")
            if timings_src.exists():
                shutil.copy(str(timings_src), str(shorts_dir / f"{stem}_timings.json"))
            stem_parts = stem.split("_", 1)
            ep_topic = stem_parts[1] if len(stem_parts) == 2 and stem_parts[0].startswith("ep") else stem
            passed, notes = validate_audio(state.case_id, slug, track="shorts", topic=ep_topic)
            log.info(f"Shorts TTS [{i + 1}/{len(md_files)}] {stem}: audio_validation passed={passed}")

    elif step == "shorts_assemble":
        from src.agents.shorts_assembler_agent import ShortsAssemblerAgent
        shorts_dir = Path(f"data/cases/{slug}/shorts")
        md_files = sorted(shorts_dir.glob("*.md")) if shorts_dir.is_dir() else []
        if not md_files:
            raise ValueError("No episode scripts — run shorts_script first")
        mp3_files = list(shorts_dir.glob("*.mp3")) if shorts_dir.is_dir() else []
        if not mp3_files:
            raise ValueError("No episode audio — run shorts_tts first")
        state = _build_state(slug)
        state.shorts_episode_paths = [str(p) for p in md_files]
        log.info(f"ShortsAssemblerAgent starting ({len(md_files)} episodes)")
        ShortsAssemblerAgent().assemble(state)

    else:
        raise ValueError(f"Unknown step: {step}")


@router.post("/{slug}/run_full")
async def run_full_pipeline(slug: str, track: str = "longform"):
    """Run all pipeline steps for a track in sequence (in background).

    track: "longform" | "shorts"

    Longform: research → characters → script → qa → tts → broll → assemble → thumbnail
    Shorts:   research → characters → shorts_plan → shorts_script → shorts_tts → shorts_assemble

    Each step runs synchronously inside a single background thread — steps chain
    automatically and stop on first failure. Returns immediately; use
    GET /api/pipeline/{slug}/job to poll status.
    """
    from src.db.models import Case
    from src.db.session import get_session

    if track not in ("longform", "shorts"):
        raise HTTPException(status_code=400, detail=f"Invalid track '{track}'. Must be 'longform' or 'shorts'.")

    _guard_already_running(slug)
    with get_session() as session:
        case = session.query(Case).filter(Case.slug == slug).first()
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")

    steps = LONGFORM_STEPS if track == "longform" else SHORTS_STEPS
    job_id = start_job(slug, f"run_full:{track}")
    log = PipelineLogger(slug, "run_full")
    log.info(f"Run full pipeline | track={track} | steps={steps} | job_id={job_id}")

    def _run():
        total = len(steps)
        for i, step in enumerate(steps):
            log.info(f"[{i + 1}/{total}] Starting: {step}")
            update_job(slug, "running", progress=int(100 * i / total))
            _run_step_core(slug, step, log)
            log.info(f"[{i + 1}/{total}] Done: {step}")
            invalidate_slug(slug)  # refresh cache after each step so UI stays live
        update_job(slug, "running", progress=100)
        log.info("All steps complete")

    t = threading.Thread(target=_run_in_thread, args=(_run, slug, "run_full", log), daemon=True)
    t.start()

    return {"started": True, "slug": slug, "track": track, "steps": steps, "job_id": job_id}


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------


@router.post("/{slug}/approve")
async def approve_step(slug: str):
    """Advance case status to the next step in the pipeline.

    Gate: when the case is leaving human_review (i.e. the script gate), the
    script's checkpoint must be "ai_validated" — meaning QA has actually run
    against whatever is currently saved (manual edit or AI draft) and passed.
    A checkpoint that is missing, still "human_edited" (edited but not
    re-validated), or "ai_flagged" (validation ran and failed) blocks approval.
    """
    import asyncio

    from src.db.models import Case
    from src.db.session import get_session

    def _do():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, f"Case '{slug}' not found"
            next_st = _next_status(case.status)
            if next_st is None:
                return None, f"No next status after '{case.status}'"

            from src.pipeline.checkpoints import get_checkpoint, mark_human_approved

            if case.status == "human_review":
                cp = get_checkpoint(str(case.id), "script")
                if not cp or cp.get("status") != "ai_validated":
                    return None, (
                        "qa_required:Script must pass QA since the last edit "
                        "before approving — run QA first"
                    )

            prev = case.status
            case.status = next_st
            session.flush()

            if prev == "human_review":
                mark_human_approved(str(case.id), "script")

            return {"slug": slug, "previous_status": prev, "new_status": next_st}, None

    data, err = await asyncio.to_thread(_do)
    if err and "not found" in err:
        raise HTTPException(status_code=404, detail=err)
    if err and err.startswith("qa_required:"):
        raise HTTPException(status_code=400, detail=err.split(":", 1)[1])
    if err:
        raise HTTPException(status_code=400, detail=err)
    invalidate_slug(slug)
    return data


@router.post("/{slug}/reject")
async def reject_step(slug: str):
    """Roll back case status to the previous step."""
    import asyncio

    from src.db.models import Case
    from src.db.session import get_session

    def _do():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, f"Case '{slug}' not found"
            prev_st = _prev_status(case.status)
            if prev_st is None:
                return None, f"No previous status before '{case.status}'"
            prev = case.status
            case_id = str(case.id)
            case.status = prev_st
            session.flush()

            if prev == "human_review":
                from src.pipeline.checkpoints import mark_human_rejected
                mark_human_rejected(case_id, "script", notes=None)

            return {"slug": slug, "previous_status": prev, "new_status": prev_st}, None

    data, err = await asyncio.to_thread(_do)
    if err and "not found" in err:
        raise HTTPException(status_code=404, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=err)
    invalidate_slug(slug)
    return data


# ---------------------------------------------------------------------------
# Unpublish — LOCAL STATE ONLY. Never calls the YouTube Data API or any
# src.agents.publish_agent code path. publish_agent.PublishAgent.run() is the
# only place that sets case.status = "published" or talks to YouTube; this
# route only ever reverses that one DB field so the dashboard stops treating
# the case as terminal. If the video needs to come down on YouTube itself,
# that must be done separately in YouTube Studio.
# ---------------------------------------------------------------------------

_UNPUBLISH_WARNING = (
    "Unpublished via dashboard — LOCAL STATE ONLY, YouTube video status was NOT "
    "changed. If the video needs to come down or be edited on YouTube itself, "
    "do that separately in YouTube Studio."
)


@router.post("/{slug}/unpublish")
async def unpublish_case(slug: str):
    """Reset case.status from 'published' back to 'ready' (its immediate
    predecessor in CaseState's CaseStatus literal — see src/pipeline/state.py).
    Purely a dashboard-tracking rollback: does not touch YouTube in any way.
    """
    import asyncio

    from src.db.models import Case
    from src.db.session import get_session
    from src.pipeline.checkpoints import mark_human_edited

    def _do():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, f"Case '{slug}' not found"
            if case.status != "published":
                return None, f"Case is not published (status is '{case.status}') — nothing to unpublish"

            case.status = "ready"
            session.flush()
            return str(case.id), None

    case_id, err = await asyncio.to_thread(_do)
    if err and "not found" in err:
        raise HTTPException(status_code=404, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=err)

    mark_human_edited(case_id, "publish", notes=_UNPUBLISH_WARNING)
    invalidate_slug(slug)

    return {
        "slug": slug,
        "previous_status": "published",
        "new_status": "ready",
        "warning": _UNPUBLISH_WARNING,
    }


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------


@router.get("/jobs")
async def list_jobs():
    """Return all running + recent finished jobs."""
    return get_all_jobs()


@router.get("/{slug}/job")
async def slug_job(slug: str):
    """Return the current job for a specific case slug."""
    job = get_job(slug)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job found for slug '{slug}'")
    return job
