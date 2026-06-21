import os

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_DAILY_FREE_LIMIT = 100
_WARN_THRESHOLD = 80


class GoogleSearchClient:
    """
    General-purpose web search via Google Custom Search — niche-agnostic,
    unlike IndianKanoonClient (court judgments only) or NewsAPIClient (news
    only). Works the same for a crime case, a mythology topic, a biography,
    anything; see CLAUDE.md "Niche Is Data Too".
    """

    def __init__(self) -> None:
        self._key = os.getenv("GOOGLE_SEARCH_API_KEY", "")
        self._cse_id = os.getenv("GOOGLE_CSE_ID", "")
        self._request_count = 0
        if not self._key or not self._cse_id:
            logger.warning(
                "GOOGLE_SEARCH_API_KEY or GOOGLE_CSE_ID not set — GoogleSearchClient will return empty results"
            )
            self._enabled = False
        else:
            self._enabled = True
        self._http = httpx.Client(timeout=15)

    def _tick(self) -> bool:
        if not self._enabled:
            return False
        self._request_count += 1
        if self._request_count >= _WARN_THRESHOLD:
            logger.warning(
                "Google Custom Search request count at {}/{} — approaching daily free-tier limit",
                self._request_count,
                _DAILY_FREE_LIMIT,
            )
        return True

    def search_case(self, case_name: str, max_results: int = 10) -> list[dict]:
        if not self._tick():
            return []
        logger.info("GoogleSearchClient search_case: '{}'", case_name)
        try:
            resp = self._http.get(
                _SEARCH_URL,
                params={
                    "key": self._key,
                    "cx": self._cse_id,
                    "q": case_name,
                    "num": min(max_results, 10),
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items") or []
            return [
                {
                    "title": item.get("title") or "",
                    "snippet": item.get("snippet") or "",
                    "url": item.get("link") or "",
                    "source": item.get("displayLink") or "",
                }
                for item in items
            ]
        except Exception as exc:
            self._handle_error(exc)
            return []

    def _handle_error(self, exc: Exception) -> None:
        msg = str(exc)
        if "429" in msg or "rateLimitExceeded" in msg:
            logger.error("Google Custom Search rate limit hit: {}", exc)
        elif "403" in msg:
            logger.error("Google Custom Search forbidden (bad key/CSE id or quota exhausted): {}", exc)
        else:
            logger.error("Google Custom Search error: {}", exc)
