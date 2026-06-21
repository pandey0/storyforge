from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import ARRAY, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ChannelProfile(Base):
    """
    A configurable content niche/channel (e.g. "Indian True Crime, Hindi").
    Holds everything that's genre/language-specific so agents never hardcode
    a niche literal — see docs/SAAS_DESIGN.md §0 (niche is data, not code).
    """
    __tablename__ = "channel_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'hi'"))

    # Longform (30-45 min documentary track)
    voice_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    section_headers: Mapped[list] = mapped_column(JSONB, nullable=False)
    case_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    word_count_range: Mapped[list] = mapped_column(JSONB, nullable=False)
    words_per_minute: Mapped[int] = mapped_column(Integer, server_default=text("125"))

    # Shorts (vertical reel track) — count/identity now planned dynamically per
    # case (EpisodePlannerAgent, Phase 20); shorts_topics is retained only as
    # reference material fed into the planner prompt, no longer iterated directly.
    shorts_topics: Mapped[list] = mapped_column(JSONB, nullable=False)
    shorts_episode_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    shorts_word_range: Mapped[list] = mapped_column(JSONB, nullable=False)
    shorts_planner_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Shared: entity/role taxonomy for character extraction
    entity_roles: Mapped[list] = mapped_column(JSONB, nullable=False)

    research_sources: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cases: Mapped[List["Case"]] = relationship("Case", back_populates="channel_profile")

    def __repr__(self) -> str:
        return f"<ChannelProfile slug={self.slug!r} name={self.name!r}>"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channel_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("channel_profiles.id"), nullable=True)
    year_of_crime: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    subject_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # the human/entity this piece centers on
    extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))   # niche-specific structured fields
    tier: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("2"))
    parent_case_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True)
    case_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    pivot_step: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), server_default=text("'queued'"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    channel_profile: Mapped[Optional["ChannelProfile"]] = relationship("ChannelProfile", back_populates="cases")
    articles: Mapped[List["Article"]] = relationship("Article", back_populates="case")
    research: Mapped[List["CaseResearch"]] = relationship("CaseResearch", back_populates="case")
    scripts: Mapped[List["Script"]] = relationship("Script", back_populates="case")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="case")
    pipeline_logs: Mapped[List["PipelineLog"]] = relationship("PipelineLog", back_populates="case")
    characters: Mapped[List["CaseCharacter"]] = relationship("CaseCharacter", back_populates="case")
    parent: Mapped[Optional["Case"]] = relationship("Case", remote_side="Case.id", foreign_keys="Case.parent_case_id", back_populates="versions")
    versions: Mapped[List["Case"]] = relationship("Case", foreign_keys="Case.parent_case_id", back_populates="parent")

    def __repr__(self) -> str:
        return f"<Case id={self.id} slug={self.slug!r} status={self.status!r}>"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), unique=True, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    story_score: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0"))
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))

    case: Mapped[Optional["Case"]] = relationship("Case", back_populates="articles")

    def __repr__(self) -> str:
        return f"<Article id={self.id} source={self.source!r} title={self.title[:40]!r}>"


class CaseResearch(Base):
    __tablename__ = "case_research"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    judgment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="research")

    def __repr__(self) -> str:
        return f"<CaseResearch id={self.id} case_id={self.case_id} source_type={self.source_type!r}>"


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    version: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("1"))
    script_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_est_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), server_default=text("'draft'"))
    qa_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qa_attempts: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), server_default=text("'human'"))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="scripts")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="script")

    def __repr__(self) -> str:
        return f"<Script id={self.id} case_id={self.case_id} version={self.version} status={self.status!r}>"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    script_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("scripts.id"), nullable=True)
    video_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    r2_video_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    r2_thumb_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    render_status: Mapped[Optional[str]] = mapped_column(String(50), server_default=text("'pending'"))
    render_started: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    render_ended: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    yt_video_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    yt_url: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    yt_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    yt_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    yt_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="videos")
    script: Mapped[Optional["Script"]] = relationship("Script", back_populates="videos")
    analytics: Mapped[List["YTAnalytics"]] = relationship("YTAnalytics", back_populates="video")

    def __repr__(self) -> str:
        return f"<Video id={self.id} case_id={self.case_id} render_status={self.render_status!r}>"


class YTAnalytics(Base):
    __tablename__ = "yt_analytics"
    __table_args__ = (UniqueConstraint("video_id", "date", name="uq_yt_analytics_video_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    video_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    views: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    watch_time_hrs: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0"))
    likes: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    comments: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    shares: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    ctr: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0"))
    avg_view_pct: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0"))
    impressions: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    subscribers_gained: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    revenue_usd: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0"))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship("Video", back_populates="analytics")

    def __repr__(self) -> str:
        return f"<YTAnalytics id={self.id} video_id={self.video_id} date={self.date} views={self.views}>"


class CaseCharacter(Base):
    __tablename__ = "case_characters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # victim/accused/lawyer/judge/witness
    image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped["Case"] = relationship("Case", back_populates="characters")

    def __repr__(self) -> str:
        return f"<CaseCharacter name={self.name!r} role={self.role!r}>"


class BRollCache(Base):
    __tablename__ = "broll_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    query: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    license: Mapped[Optional[str]] = mapped_column(String(100), server_default=text("'CC0'"))
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    file_size_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<BRollCache id={self.id} query={self.query!r} source={self.source!r}>"


class PipelineLog(Base):
    __tablename__ = "pipeline_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True)
    agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[Optional["Case"]] = relationship("Case", back_populates="pipeline_logs")

    def __repr__(self) -> str:
        return f"<PipelineLog id={self.id} agent={self.agent!r} action={self.action!r} status={self.status!r}>"


class StepCheckpoint(Base):
    """
    Generic human<->AI validation state for one (case, step) pair. Every
    pipeline step plugs into this same table instead of inventing its own
    override/validation/approval pattern — see docs/TRACKER.md Phase 21.

    status: ai_generated | human_edited | ai_validated | ai_flagged |
            human_approved | human_rejected
    edited_by: who made the most recent change — "ai" | "human"
    """
    __tablename__ = "step_checkpoints"
    __table_args__ = (UniqueConstraint("case_id", "step", name="uq_checkpoint_case_step"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'ai_generated'"))
    edited_by: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<StepCheckpoint case_id={self.case_id} step={self.step!r} status={self.status!r}>"


