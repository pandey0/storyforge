from __future__ import annotations

import asyncio

import feedparser
from fastapi import APIRouter

router = APIRouter(prefix="/topics", tags=["topics"])

_RSS_FEEDS = {
    "ndtv": "https://feeds.feedburner.com/ndtvnews-top-stories",
    "toi": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "indian_express": "https://indianexpress.com/section/india/feed/",
    "the_hindu": "https://www.thehindu.com/news/national/?service=rss",
    "india_today": "https://www.indiatoday.in/rss/1206513",
    "hindustan_times": "https://www.hindustantimes.com/rss/topnews/rssfeed.xml",
    "scroll": "https://scroll.in/feed",
    "the_wire": "https://thewire.in/feed",
    "livelaw": "https://www.livelaw.in/feed",
}


def _rss_search(q: str, limit: int) -> list[dict]:
    """Pull recent entries from RSS feeds, filtered by query when specific enough."""
    words = [k.lower() for k in q.split() if len(k) > 3] if q else []
    # Only keyword-filter for specific queries (3+ meaningful words).
    # Short/generic queries return recent articles so "crime" doesn't miss "murder" headlines.
    strict = len(words) >= 3
    results: list[dict] = []
    seen: set[str] = set()

    for source, url in _RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = entry.get("title") or ""
                summary = entry.get("summary") or ""
                link = entry.get("link") or ""
                if not link or link in seen:
                    continue
                text = (title + " " + summary).lower()
                if strict and not any(w in text for w in words):
                    continue
                seen.add(link)
                results.append({
                    "title": title,
                    "snippet": summary[:200],
                    "url": link,
                    "source": source,
                    "type": "news",
                })
                if len(results) >= limit:
                    return results
        except Exception:
            continue

    return results


@router.get("/search")
async def search_topics(q: str = "", language: str = "en", limit: int = 10):
    """
    Search for topic ideas using RSS feeds from major Indian news outlets.
    No API keys required. Returns [{title, snippet, url, source, type}].
    """

    def _fetch():
        seen_urls: set[str] = set()
        results: list[dict] = []
        for item in _rss_search(q, limit):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)
        return results[:limit]

    return await asyncio.to_thread(_fetch)
