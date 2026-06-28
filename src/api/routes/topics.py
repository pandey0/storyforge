from __future__ import annotations

import asyncio

import feedparser
import httpx
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
    # Only filter when query is specific (3+ meaningful words); short/generic queries
    # return recent articles unfiltered so "crime" doesn't miss "murder" headlines
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


def _wikipedia_search(q: str, limit: int) -> list[dict]:
    """Wikipedia open search — free, no key, good for historical topics."""
    if not q:
        return []
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": q,
                "limit": limit,
                "namespace": 0,
                "format": "json",
            },
            headers={"User-Agent": "StoryForge/1.0 (content research tool; contact@storyforge.dev)"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        snippets = data[2] if len(data) > 2 else []
        urls = data[3] if len(data) > 3 else []
        return [
            {
                "title": titles[i],
                "snippet": snippets[i] if i < len(snippets) else "",
                "url": urls[i] if i < len(urls) else "",
                "source": "wikipedia",
                "type": "reference",
            }
            for i in range(len(titles))
        ]
    except Exception:
        return []


@router.get("/search")
async def search_topics(q: str = "", language: str = "en", limit: int = 10):
    """
    Search for real-world topics/events to inspire case creation.
    Sources: RSS feeds from major Indian news outlets + Wikipedia open search.
    No API keys required. Returns [{title, snippet, url, source, type}].
    """

    def _fetch():
        seen_urls: set[str] = set()
        results: list[dict] = []

        for item in _rss_search(q, limit):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)

        if len(results) < limit:
            for item in _wikipedia_search(q, limit - len(results)):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)

        # NewsAPI as optional bonus if key present
        try:
            from src.scrapers.news_api import NewsAPIClient
            news = NewsAPIClient()
            if news._enabled and q:
                for a in news.search_recent(q, days_back=30, max_results=limit):
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
