from __future__ import annotations

import os
from datetime import date, datetime, timezone

from loguru import logger

from src.db.models import Video, YTAnalytics
from src.db.session import get_session


class AnalyticsAgent:
    """Syncs YouTube analytics to DB. Requires YouTube Data API v3."""

    def run(self, session=None) -> None:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            logger.warning("AnalyticsAgent: YOUTUBE_API_KEY not set — skipping sync")
            return

        try:
            service = self._get_service()
        except Exception as exc:
            logger.error("AnalyticsAgent: failed to build YT service: {}", exc)
            return

        with get_session() as db:
            videos = db.query(Video).filter(Video.yt_video_id.isnot(None)).all()
            if not videos:
                logger.info("AnalyticsAgent: no uploaded videos to sync")
                return

            for video in videos:
                try:
                    self._sync_video(service, video, db)
                except Exception as exc:
                    logger.warning("AnalyticsAgent: sync failed for {}: {}", video.yt_video_id, exc)

        logger.info("AnalyticsAgent: sync complete for {} videos", len(videos))

    def _get_service(self):
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

    def _sync_video(self, service, video: Video, session) -> None:
        today = date.today()

        response = service.videos().list(
            part="statistics",
            id=video.yt_video_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            logger.warning("AnalyticsAgent: no stats returned for {}", video.yt_video_id)
            return

        stats = items[0].get("statistics", {})
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        existing = session.query(YTAnalytics).filter(
            YTAnalytics.video_id == video.id,
            YTAnalytics.date == today,
        ).first()

        if existing:
            existing.views = views
            existing.likes = likes
            existing.comments = comments
            existing.synced_at = datetime.now(timezone.utc)
        else:
            row = YTAnalytics(
                video_id=video.id,
                date=today,
                views=views,
                likes=likes,
                comments=comments,
                synced_at=datetime.now(timezone.utc),
            )
            session.add(row)

        logger.info("AnalyticsAgent: synced {} → {} views", video.yt_video_id, views)
