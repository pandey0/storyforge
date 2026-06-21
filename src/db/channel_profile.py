from __future__ import annotations

from src.db.models import Case, ChannelProfile
from src.db.session import get_session

DEFAULT_PROFILE_SLUG = "indian-true-crime-hindi"


def get_profile_for_case(slug: str) -> ChannelProfile:
    """
    Return the ChannelProfile for case *slug*. Falls back to DEFAULT_PROFILE_SLUG
    if the case has no channel_profile_id set (legacy/unconfigured case) — agents
    must always go through this helper, never hardcode niche content themselves.
    """
    with get_session() as session:
        case = session.query(Case).filter_by(slug=slug).one()
        if case.channel_profile_id is not None:
            profile = session.query(ChannelProfile).filter_by(id=case.channel_profile_id).first()
            if profile is not None:
                session.expunge(profile)
                return profile

        profile = session.query(ChannelProfile).filter_by(slug=DEFAULT_PROFILE_SLUG).first()
        if profile is None:
            raise RuntimeError(
                f"No channel_profile assigned to case '{slug}' and default profile "
                f"'{DEFAULT_PROFILE_SLUG}' not found — run `python -m src.db.seed_default_profile`"
            )
        session.expunge(profile)
        return profile
