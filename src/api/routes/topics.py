from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("/search")
async def search_topics(q: str = "", language: str = "en", limit: int = 10):
    """
    Search for real-world topics/events to inspire case creation.
    Combines Google CSE (web) + NewsAPI (recent headlines).
    Returns deduplicated list: [{title, snippet, url, source, type}]
    """

    def _fetch():
        results: list[dict] = []
        seen_urls: set[str] = set()

        # --- Google CSE: recent results ---
        try:
            from src.scrapers.google_search import GoogleSearchClient
            client = GoogleSearchClient()
            if client._enabled:
                key = client._key
                cse_id = client._cse_id
                import httpx
                params: dict = {
                    "key": key,
                    "cx": cse_id,
                    "q": q or "trending events news 2024",
                    "num": min(limit, 10),
                    "dateRestrict": "m1",   # last month
                    "sort": "date",
                }
                if language.startswith("hi"):
                    params["lr"] = "lang_hi"
                    params["gl"] = "in"
                elif language.startswith("ta"):
                    params["lr"] = "lang_ta"
                    params["gl"] = "in"
                resp = httpx.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=15,
                )
                if resp.status_code == 200:
                    for item in resp.json().get("items") or []:
                        url = item.get("link") or ""
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append({
                                "title": item.get("title") or "",
                                "snippet": item.get("snippet") or "",
                                "url": url,
                                "source": item.get("displayLink") or "",
                                "type": "web",
                            })
        except Exception:
            pass

        # --- NewsAPI: recent headlines ---
        try:
            from src.scrapers.news_api import NewsAPIClient
            news = NewsAPIClient()
            if news._enabled and q:
                articles = news.search_recent(q, days_back=30, max_results=limit)
                for a in articles:
                    url = a.get("url") or ""
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({
                            "title": a.get("title") or "",
                            "snippet": a.get("description") or "",
                            "url": url,
                            "source": a.get("source") or "",
                            "type": "news",
                        })
        except Exception:
            pass

        return results[:limit]

    return await asyncio.to_thread(_fetch)
