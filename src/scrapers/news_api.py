import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger
from newsapi import NewsApiClient

load_dotenv()

_REQUEST_LIMIT = 100
_WARN_THRESHOLD = 80


class NewsAPIClient:
    def __init__(self):
        self._key = os.getenv("NEWS_API_KEY", "")
        self._request_count = 0
        if not self._key:
            logger.warning("NEWS_API_KEY not set — NewsAPIClient will return empty results")
            self._client = None
        else:
            self._client = NewsApiClient(api_key=self._key)

    def _tick(self) -> bool:
        if self._client is None:
            return False
        self._request_count += 1
        if self._request_count >= _WARN_THRESHOLD:
            logger.warning(
                "NewsAPI request count at {}/{} — approaching daily limit",
                self._request_count,
                _REQUEST_LIMIT,
            )
        logger.debug("NewsAPI request #{}", self._request_count)
        return True

    def to_article_dict(self, raw: dict, source_name: str) -> dict:
        return {
            "title": raw.get("title") or "",
            "content": raw.get("content") or raw.get("description") or "",
            "url": raw.get("url") or "",
            "source": source_name,
            "published_at": raw.get("publishedAt") or "",
        }

    def search_recent(self, query: str, days_back: int = 7) -> list[dict]:
        if not self._tick():
            return []
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        logger.info("NewsAPI search_recent: query='{}' days_back={}", query, days_back)
        try:
            resp = self._client.get_everything(
                q=query,
                from_param=from_date,
                language="en",
                sort_by="relevancy",
                page_size=20,
            )
            articles = resp.get("articles") or []
            return [self.to_article_dict(a, (a.get("source") or {}).get("name", "")) for a in articles]
        except Exception as exc:
            self._handle_error(exc)
            return []

    def search_case(self, case_name: str) -> list[dict]:
        if not self._tick():
            return []
        logger.info("NewsAPI search_case: '{}'", case_name)
        try:
            resp = self._client.get_everything(
                q=case_name,
                language="en",
                sort_by="relevancy",
                page_size=20,
            )
            articles = resp.get("articles") or []
            return [self.to_article_dict(a, (a.get("source") or {}).get("name", "")) for a in articles]
        except Exception as exc:
            self._handle_error(exc)
            return []

    def get_top_headlines(self) -> list[dict]:
        return []

    def _handle_error(self, exc: Exception) -> None:
        msg = str(exc).lower()
        if "429" in msg or "rateLimited" in str(exc):
            logger.error("NewsAPI rate limit hit: {}", exc)
        elif "401" in msg or "apiKeyInvalid" in str(exc):
            logger.error("NewsAPI invalid key: {}", exc)
        else:
            logger.error("NewsAPI error: {}", exc)
