from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _profile_to_dict(p) -> dict:
    return {
        "id": str(p.id),
        "slug": p.slug,
        "name": p.name,
        "language": p.language,
        "voice_system_prompt": p.voice_system_prompt or "",
        "section_headers": p.section_headers or [],
        "case_prompt_template": p.case_prompt_template or "",
        "word_count_range": p.word_count_range or [4000, 6500],
        "shorts_topics": p.shorts_topics or [],
        "shorts_episode_prompt_template": p.shorts_episode_prompt_template or "",
        "shorts_word_range": p.shorts_word_range or [200, 300],
        "shorts_planner_prompt": p.shorts_planner_prompt or "",
        "entity_roles": p.entity_roles or [],
        "research_sources": p.research_sources or [],
    }


def _make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "profile"


@router.get("")
async def list_profiles():
    """List all channel profiles."""
    import asyncio

    def _fetch():
        from src.db.models import ChannelProfile
        from src.db.session import get_session
        with get_session() as session:
            rows = session.query(ChannelProfile).order_by(ChannelProfile.name).all()
            return [{"id": str(p.id), "slug": p.slug, "name": p.name, "language": p.language} for p in rows]

    return await asyncio.to_thread(_fetch)


@router.get("/{slug}")
async def get_profile(slug: str):
    """Get full channel profile."""
    import asyncio

    def _fetch():
        from src.db.models import ChannelProfile
        from src.db.session import get_session
        with get_session() as session:
            p = session.query(ChannelProfile).filter_by(slug=slug).first()
            if not p:
                return None
            return _profile_to_dict(p)

    result = await asyncio.to_thread(_fetch)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Profile '{slug}' not found")
    return result


class ProfileCreate(BaseModel):
    name: str
    language: str = "hi"
    voice_system_prompt: str = ""
    section_headers: list[str] = []
    case_prompt_template: str = ""
    word_count_range: list[int] = [4000, 6500]
    shorts_topics: list[dict] = []
    shorts_episode_prompt_template: str = ""
    shorts_word_range: list[int] = [200, 300]
    shorts_planner_prompt: str = ""
    entity_roles: list[dict] = []
    research_sources: list[dict] = []


@router.post("")
async def create_profile(body: ProfileCreate):
    """Create a new channel profile."""
    import asyncio

    def _create():
        from src.db.models import ChannelProfile
        from src.db.session import get_session
        with get_session() as session:
            base_slug = _make_slug(body.name)
            slug = base_slug
            n = 2
            while session.query(ChannelProfile).filter_by(slug=slug).first():
                slug = f"{base_slug}-{n}"
                n += 1

            p = ChannelProfile(
                id=uuid.uuid4(),
                slug=slug,
                name=body.name,
                language=body.language,
                voice_system_prompt=body.voice_system_prompt,
                section_headers=body.section_headers,
                case_prompt_template=body.case_prompt_template,
                word_count_range=body.word_count_range,
                shorts_topics=body.shorts_topics,
                shorts_episode_prompt_template=body.shorts_episode_prompt_template,
                shorts_word_range=body.shorts_word_range,
                shorts_planner_prompt=body.shorts_planner_prompt,
                entity_roles=body.entity_roles,
                research_sources=body.research_sources,
            )
            session.add(p)
            session.commit()
            session.refresh(p)
            return _profile_to_dict(p)

    return await asyncio.to_thread(_create)


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    voice_system_prompt: Optional[str] = None
    section_headers: Optional[list[str]] = None
    case_prompt_template: Optional[str] = None
    word_count_range: Optional[list[int]] = None
    shorts_topics: Optional[list[dict]] = None
    shorts_episode_prompt_template: Optional[str] = None
    shorts_word_range: Optional[list[int]] = None
    shorts_planner_prompt: Optional[str] = None
    entity_roles: Optional[list[dict]] = None
    research_sources: Optional[list[dict]] = None


@router.put("/{slug}")
async def update_profile(slug: str, body: ProfileUpdate):
    """Partial update of a channel profile."""
    import asyncio

    def _update():
        from src.db.models import ChannelProfile
        from src.db.session import get_session
        with get_session() as session:
            p = session.query(ChannelProfile).filter_by(slug=slug).first()
            if not p:
                return None
            for field, value in body.model_dump(exclude_none=True).items():
                setattr(p, field, value)
            session.commit()
            session.refresh(p)
            return _profile_to_dict(p)

    result = await asyncio.to_thread(_update)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Profile '{slug}' not found")
    return result


@router.delete("/{slug}")
async def delete_profile(slug: str):
    """Delete a profile. Refuses if cases reference it."""
    import asyncio

    def _delete():
        from src.db.models import ChannelProfile, Case
        from src.db.session import get_session
        with get_session() as session:
            p = session.query(ChannelProfile).filter_by(slug=slug).first()
            if not p:
                return ("not_found", 0)
            count = session.query(Case).filter_by(channel_profile_id=p.id).count()
            if count > 0:
                return ("in_use", count)
            session.delete(p)
            session.commit()
            return ("deleted", 0)

    status, count = await asyncio.to_thread(_delete)
    if status == "not_found":
        raise HTTPException(status_code=404, detail=f"Profile '{slug}' not found")
    if status == "in_use":
        raise HTTPException(status_code=400, detail=f"Profile used by {count} case(s) — reassign them first")
    return {"deleted": True, "slug": slug}
