from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz
from loguru import logger

from src.db.models import Case, Video
from src.db.session import get_session
from src.pipeline.state import CaseState

IST = pytz.timezone("Asia/Kolkata")


def build_description(case, state: CaseState) -> str:
    slug = case.slug
    research_path = Path(f"data/cases/{slug}/research.json")
    sources_block = ""
    if research_path.exists():
        try:
            data = json.loads(research_path.read_text(encoding="utf-8"))
            sources_dict = data.get("sources", {})
            source_urls: list[str] = []
            if isinstance(sources_dict, dict):
                for items in sources_dict.values():
                    if isinstance(items, list):
                        for item in items:
                            url = item.get("url") or item.get("source_url") or item.get("link", "") if isinstance(item, dict) else ""
                            if url:
                                source_urls.append(url)
            if source_urls:
                urls = "\n".join(f"• {u}" for u in source_urls[:20])
                sources_block = f"📚 स्रोत:\n{urls}\n"
        except Exception:
            pass

    location_str = case.location or "भारत"
    year_str = str(case.year_of_crime) if case.year_of_crime else "हाल के वर्षों में"
    case_type_str = case.extra.get("case_type") or "आपराधिक मामले"

    slug_tag = slug.replace("-", "").replace("_", "").title()

    desc = f"""{case.name} — एक डॉक्युमेंट्री जांच।

इस एपिसोड में हम {case.name} की पड़ताल करते हैं, जो {location_str} में {year_str} हुआ।

⚠️ सामग्री नोट: इस वीडियो में {case_type_str} से जुड़े आपराधिक मामलों पर चर्चा है। दर्शक विवेक से देखें।

{sources_block}
🔔 और हिंदी True Crime डॉक्युमेंट्री के लिए subscribe करें।

#हिंदीTrueCrime #TrueCrime #India #Documentary #{slug_tag} #IndianCrime #SachchiGhatna"""
    return desc.strip()


def build_tags(case) -> list[str]:
    base_tags = [
        "hindi true crime",
        "true crime india hindi",
        "भारतीय अपराध",
        "हिंदी डॉक्युमेंट्री",
        "सच्ची घटना",
        "crime documentary hindi",
        case.name,
    ]
    if case.location:
        base_tags.append(case.location.split(",")[0].strip())
    case_type = case.extra.get("case_type")
    if case_type:
        base_tags.append(case_type)
    return base_tags[:15]


class PublishAgent:
    def run(self, state: CaseState, schedule_time: Optional[datetime] = None) -> CaseState:
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == state.slug).first()
            if case is None:
                raise ValueError(f"Case not found: {state.slug}")

            logger.info(f"PublishAgent: uploading video for {state.slug}")

            service = self._get_youtube_service()
            metadata = self._build_metadata(state, case)

            video_path = state.video_path
            if not video_path:
                raise ValueError("state.video_path is not set")

            video_id = self._upload_video(service, video_path, metadata)
            logger.success(f"PublishAgent: uploaded → video_id={video_id}")

            if state.thumbnail_path and os.path.exists(state.thumbnail_path):
                self._set_thumbnail(service, video_id, state.thumbnail_path)

            if schedule_time is None:
                now_ist = datetime.now(IST)
                schedule_time = (now_ist + timedelta(days=1)).replace(
                    hour=18, minute=0, second=0, microsecond=0
                )

            self._schedule_publish(service, video_id, schedule_time)

            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            self._update_db(state, video_id, yt_url, session, case, schedule_time, metadata)

            case.status = "published"
            state.yt_video_id = video_id
            state.status = "published"

        logger.success(f"PublishAgent: done. URL={yt_url}")
        return state

    def _get_youtube_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.getenv("YOUTUBE_CLIENT_ID"),
            client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        return build("youtube", "v3", credentials=creds)

    def _build_metadata(self, state: CaseState, case) -> dict:
        title = f"{case.name} | हिंदी True Crime Documentary"
        title = title[:100]
        tags = build_tags(case)
        description = build_description(case, state)

        return {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "25",
                "defaultLanguage": "hi",
                "defaultAudioLanguage": "hi",
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
            },
        }

    def _upload_video(self, service, video_path: str, metadata: dict) -> str:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(
            video_path,
            chunksize=-1,
            resumable=True,
            mimetype="video/mp4",
        )
        request = service.videos().insert(
            part=",".join(metadata.keys()),
            body=metadata,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")

        return response["id"]

    def _set_thumbnail(self, service, video_id: str, thumbnail_path: str) -> None:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        service.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        logger.info(f"Thumbnail set for video_id={video_id}")

    def _schedule_publish(self, service, video_id: str, publish_at: datetime) -> None:
        if publish_at.tzinfo is None:
            publish_at = IST.localize(publish_at)
        publish_utc = publish_at.astimezone(pytz.utc)
        publish_str = publish_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        service.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "scheduled",
                    "publishAt": publish_str,
                },
            },
        ).execute()
        logger.info(f"Scheduled publish at {publish_str} for video_id={video_id}")

    def _update_db(
        self,
        state: CaseState,
        video_id: str,
        yt_url: str,
        session,
        case,
        schedule_time: Optional[datetime],
        metadata: dict,
    ) -> None:
        video = (
            session.query(Video)
            .filter(Video.case_id == case.id)
            .order_by(Video.created_at.desc())
            .first()
        )
        if video is None:
            logger.warning("No Video row found — skipping DB update for video metadata")
            return

        video.yt_video_id = video_id
        video.yt_url = yt_url
        video.yt_title = metadata["snippet"]["title"]
        video.yt_description = metadata["snippet"]["description"]
        video.yt_tags = metadata["snippet"]["tags"]

        if schedule_time is not None:
            if schedule_time.tzinfo is None:
                schedule_time = IST.localize(schedule_time)
            video.scheduled_at = schedule_time
        else:
            video.published_at = datetime.now(pytz.utc)
