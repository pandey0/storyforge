from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
async def list_profiles():
    """List all channel profiles for the case-creation picker — niche/language
    is selected here, never hardcoded. See docs/SAAS_DESIGN.md §0."""
    import asyncio

    def _fetch():
        from src.db.models import ChannelProfile
        from src.db.session import get_session

        with get_session() as session:
            rows = session.query(ChannelProfile).order_by(ChannelProfile.name).all()
            return [
                {"id": str(p.id), "slug": p.slug, "name": p.name, "language": p.language}
                for p in rows
            ]

    return await asyncio.to_thread(_fetch)
