from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

CaseStatus = Literal[
    "queued",
    "research",
    "scripting",
    "qa_review",
    "human_review",
    "tts",
    "broll",
    "video",
    "thumbnail",
    "ready",
    "published",
    "failed",
]


@dataclass
class CaseState:
    slug: str
    case_id: str
    name: str
    status: str
    research_path: Optional[str] = field(default=None)
    script_path: Optional[str] = field(default=None)
    draft_script_path: Optional[str] = field(default=None)
    audio_path: Optional[str] = field(default=None)
    timings_path: Optional[str] = field(default=None)
    broll_dir: Optional[str] = field(default=None)
    video_path: Optional[str] = field(default=None)
    thumbnail_path: Optional[str] = field(default=None)
    yt_video_id: Optional[str] = field(default=None)
    shorts_script_path: Optional[str] = field(default=None)
    shorts_video_path: Optional[str] = field(default=None)
    shorts_episode_paths: list[str] = field(default_factory=list)
    shorts_video_paths: list[str] = field(default_factory=list)
    shorts_plan_path: Optional[str] = field(default=None)
    error: Optional[str] = field(default=None)

    @property
    def case_dir(self) -> str:
        return f"data/cases/{self.slug}/"

    @classmethod
    def from_db_case(cls, case_row) -> "CaseState":
        return cls(
            slug=case_row.slug,
            case_id=str(case_row.id),
            name=case_row.name,
            status=case_row.status,
        )
