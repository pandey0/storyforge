from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.models import Case, Script, Video
from src.db.session import get_session
from src.api.cache import ttl_cache, invalidate_slug

router = APIRouter(prefix="/cases", tags=["cases"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CaseCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    year_of_crime: Optional[int] = None
    location: Optional[str] = None
    subject_name: Optional[str] = None
    channel_profile_id: Optional[uuid.UUID] = None
    tier: Optional[int] = 2
    extra: dict[str, Any] = {}


class StatusUpdate(BaseModel):
    status: str


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:150]


def _case_to_dict(case: Case, script_count: int = 0, video_count: int = 0) -> dict:
    return {
        "id": str(case.id),
        "slug": case.slug,
        "name": case.name,
        "year_of_crime": case.year_of_crime,
        "location": case.location,
        "subject_name": case.subject_name,
        "extra": case.extra,
        "victim_age": case.extra.get("subject_age"),
        "victim_profession": case.extra.get("subject_profession"),
        "perpetrator": case.extra.get("perpetrator"),
        "case_type": case.extra.get("case_type"),
        "tier": case.tier,
        "status": case.status,
        "notes": case.notes,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "script_count": script_count,
        "video_count": video_count,
    }


def _file_info(path: Path) -> dict:
    if path.exists() and path.is_file():
        size_bytes = path.stat().st_size
        return {"exists": True, "size_mb": round(size_bytes / (1024 * 1024), 3)}
    return {"exists": False, "size_mb": None}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_cases(track: Optional[str] = None):
    """Return cases ordered by updated_at desc. ?track=longform|shorts filters by case_type."""
    import asyncio

    def _fetch():
        with get_session() as session:
            q = session.query(Case).order_by(Case.updated_at.desc())
            if track:
                # Show cases matching track OR untagged (backwards compat)
                from sqlalchemy import or_, cast, String
                from sqlalchemy.dialects.postgresql import JSONB
                q = q.filter(
                    or_(
                        Case.extra["case_type"].as_string() == track,
                        Case.extra["case_type"].is_(None),
                    )
                )
            cases = q.all()
            result = []
            for c in cases:
                sc = session.query(Script).filter(Script.case_id == c.id).count()
                vc = session.query(Video).filter(Video.case_id == c.id).count()
                result.append(_case_to_dict(c, sc, vc))
            return result

    return await asyncio.to_thread(_fetch)


@router.get("/{slug}")
async def get_case(slug: str):
    """Return a single case with script + video counts."""
    import asyncio

    def _fetch():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None
            sc = session.query(Script).filter(Script.case_id == case.id).count()
            vc = session.query(Video).filter(Video.case_id == case.id).count()
            return _case_to_dict(case, sc, vc)

    data = await asyncio.to_thread(_fetch)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    return data


@router.get("/{slug}/profile")
async def get_case_profile(slug: str):
    """
    Return the case's resolved ChannelProfile fields the frontend needs to
    render dynamically (shorts topics, entity roles) — never a hardcoded
    frontend list. See docs/SAAS_DESIGN.md §0.
    """
    import asyncio
    from src.db.channel_profile import get_profile_for_case

    def _fetch():
        try:
            profile = get_profile_for_case(slug)
        except Exception:
            return None
        return {
            "slug": profile.slug,
            "name": profile.name,
            "language": profile.language,
            "shorts_topics": [
                {"slug": t["slug"], "label": t["label"]} for t in profile.shorts_topics
            ],
            "entity_roles": [
                {"slug": r["slug"], "label": r["label"]} for r in profile.entity_roles
            ],
        }

    data = await asyncio.to_thread(_fetch)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found or no channel profile")
    return data


@router.post("", status_code=201)
async def create_case(body: CaseCreate):
    """Create a new case. Auto-generates slug from name if not provided."""
    import asyncio

    slug = body.slug or _slugify(body.name)

    def _create():
        with get_session() as session:
            existing = session.query(Case).filter(Case.slug == slug).first()
            if existing:
                return None, f"Case with slug '{slug}' already exists"
            case = Case(
                slug=slug,
                name=body.name,
                year_of_crime=body.year_of_crime,
                location=body.location,
                subject_name=body.subject_name,
                channel_profile_id=body.channel_profile_id,
                tier=body.tier if body.tier is not None else 2,
                extra=body.extra,
                status="queued",
            )
            session.add(case)
            session.flush()
            return _case_to_dict(case), None

    data, err = await asyncio.to_thread(_create)
    if err:
        raise HTTPException(status_code=409, detail=err)
    invalidate_slug(slug)
    return data


@router.put("/{slug}/status")
async def update_status(slug: str, body: StatusUpdate):
    """Update the status of a case."""
    import asyncio

    def _update():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None
            case.status = body.status
            session.flush()
            return _case_to_dict(case)

    data = await asyncio.to_thread(_update)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    invalidate_slug(slug)
    return data


@router.get("/{slug}/files")
async def get_case_files(slug: str):
    """Return file existence and sizes for all generated artifacts."""
    import asyncio

    @ttl_cache(seconds=10)
    def _check_files():
        base = Path(f"data/cases/{slug}")

        research = _file_info(base / "research.json")
        shorts_plan_path = base / "shorts_plan.json"
        shorts_plan = _file_info(shorts_plan_path)
        shorts_plan_count = 0
        if shorts_plan_path.exists():
            try:
                shorts_plan_count = len(json.loads(shorts_plan_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                shorts_plan_count = 0
        script_draft = _file_info(base / "script_draft.md")
        script_manual = _file_info(base / "script_manual.md")
        audio = _file_info(base / "audio" / "voiceover.mp3")
        timings = _file_info(base / "audio" / "word_timings.json")
        video = _file_info(base / "output" / "video_final.mp4")
        thumbnail = _file_info(base / "output" / "thumbnail.jpg")

        # Count characters from DB (not files — images may not exist yet)
        from src.db.models import CaseCharacter
        from src.db.session import get_session
        with get_session() as session:
            from src.db.models import Case as _Case
            _case = session.query(_Case).filter(_Case.slug == slug).first()
            characters_count = (
                session.query(CaseCharacter).filter_by(case_id=_case.id).count()
                if _case else 0
            )

        broll_dir = base / "broll"
        broll_clips = sorted(
            f.name for f in broll_dir.iterdir()
            if f.suffix in {".mp4", ".mov", ".webm"}
        ) if broll_dir.is_dir() else []

        shorts_dir = base / "shorts"
        shorts_episodes = sorted(
            f.name for f in shorts_dir.iterdir()
            if f.suffix == ".mp4"
        ) if shorts_dir.is_dir() else []

        # Episode scripts (.md files in shorts/)
        shorts_scripts_list = sorted(
            f.name for f in shorts_dir.iterdir()
            if f.suffix == ".md"
        ) if shorts_dir.is_dir() else []

        # Episode audio (.mp3 files in shorts/)
        shorts_audio_list = sorted(
            f.name for f in shorts_dir.iterdir()
            if f.suffix == ".mp3"
        ) if shorts_dir.is_dir() else []

        return {
            "slug": slug,
            "research": research,
            "script_draft": script_draft,
            "script_manual": script_manual,
            "audio": audio,
            "timings": timings,
            "video": video,
            "thumbnail": thumbnail,
            "characters_count": characters_count,
            "shorts_plan": shorts_plan,
            "shorts_plan_count": shorts_plan_count,
            "broll_clips": broll_clips,
            "shorts_episodes": shorts_episodes,
            "shorts_scripts": shorts_scripts_list,
            "shorts_script_count": len(shorts_scripts_list),
            "shorts_audio": shorts_audio_list,
            "shorts_audio_count": len(shorts_audio_list),
        }

    return await asyncio.to_thread(_check_files)


# ---------------------------------------------------------------------------
# Case versioning / branching
# ---------------------------------------------------------------------------


class BranchBody(BaseModel):
    pivot_step: str  # research | script | tts
    reason: Optional[str] = None


@router.get("/{slug}/versions")
async def get_case_versions(slug: str):
    """Return parent case + all child versions, ordered by case_version."""
    import asyncio

    def _fetch():
        from src.db.models import Case
        from src.db.session import get_session

        with get_session() as s:
            # Find root case (either this is root, or find its parent)
            case = s.query(Case).filter_by(slug=slug).first()
            if not case:
                return None

            # Find root
            root = case
            while root.parent_case_id:
                root = s.query(Case).filter_by(id=root.parent_case_id).first()
                if not root:
                    break

            if not root:
                return None

            # Get all versions (root + children)
            children = s.query(Case).filter_by(parent_case_id=root.id).order_by(Case.case_version).all()
            all_versions = [root] + children

            return {
                "root_slug": root.slug,
                "versions": [
                    {
                        **_case_to_dict(v),
                        "is_root": v.id == root.id,
                        "pivot_step": v.pivot_step,
                        "case_version": v.case_version,
                    }
                    for v in all_versions
                ]
            }

    result = await asyncio.to_thread(_fetch)
    if result is None:
        raise HTTPException(404, f"Case not found: {slug}")
    return result


@router.post("/{slug}/branch", status_code=201)
async def branch_case(slug: str, body: BranchBody):
    """
    Create a child case (version) branching at pivot_step.
    Copies relevant files from parent, starts child pipeline from pivot_step.
    """
    import asyncio
    from src.api.versions import PIVOT_COPY_MAP, PIVOT_CHILD_STATUS

    VALID_PIVOTS = {"research", "script", "tts"}
    if body.pivot_step not in VALID_PIVOTS:
        raise HTTPException(400, f"pivot_step must be one of: {VALID_PIVOTS}")

    def _branch():
        from src.db.models import Case
        from src.db.session import get_session

        with get_session() as s:
            parent = s.query(Case).filter_by(slug=slug).first()
            if not parent:
                return None, f"Case not found: {slug}"

            # Find root for version numbering
            root = parent
            while root.parent_case_id:
                root = s.query(Case).filter_by(id=root.parent_case_id).first()
                if not root:
                    root = parent
                    break

            # Count existing versions under this root
            sibling_count = s.query(Case).filter_by(parent_case_id=root.id).count()
            new_version = sibling_count + 2  # root is v1, first child is v2

            # New child slug and name
            child_slug = f"{root.slug}-v{new_version}"
            child_name = f"{root.name} (v{new_version})"

            # Check no collision
            if s.query(Case).filter_by(slug=child_slug).first():
                return None, f"Version already exists: {child_slug}"

            # Create child case
            child = Case(
                slug=child_slug,
                name=child_name,
                year_of_crime=parent.year_of_crime,
                location=parent.location,
                subject_name=parent.subject_name,
                channel_profile_id=parent.channel_profile_id,
                extra=dict(parent.extra),
                tier=parent.tier,
                status=PIVOT_CHILD_STATUS.get(body.pivot_step, "queued"),
                notes=body.reason or f"Branched from {slug} at {body.pivot_step}",
                parent_case_id=root.id,
                case_version=new_version,
                pivot_step=body.pivot_step,
            )
            s.add(child)
            s.flush()

            # Copy files from parent
            parent_dir = Path(f"data/cases/{slug}")
            child_dir = Path(f"data/cases/{child_slug}")
            child_dir.mkdir(parents=True, exist_ok=True)

            files_to_copy = PIVOT_COPY_MAP.get(body.pivot_step, [])
            copied = []
            for rel_path in files_to_copy:
                src = parent_dir / rel_path
                if src.exists():
                    dst = child_dir / rel_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied.append(rel_path)

            return {**_case_to_dict(child), "pivot_step": body.pivot_step, "case_version": new_version, "files_copied": copied}, None

    data, err = await asyncio.to_thread(_branch)
    if err:
        raise HTTPException(409, err)
    invalidate_slug(slug)
    return data
