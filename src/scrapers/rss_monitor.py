from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import feedparser
from dotenv import load_dotenv
from loguru import logger

from src.db.models import Article

load_dotenv()

RSS_FEEDS: dict[str, str] = {
    "ndtv": "https://feeds.feedburner.com/ndtvnews-crime",
    "toi": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "indian_express": "https://indianexpress.com/section/india/feed/",
    "the_hindu": "https://www.thehindu.com/news/national/?service=rss",
    "india_today": "https://www.indiatoday.in/rss/1206513",
    "hindustan_times": "https://www.hindustantimes.com/feeds/rss/crime/rssfeed.xml",
    "scroll": "https://scroll.in/feed",
    "the_wire": "https://thewire.in/feed",
    "livelaw": "https://www.livelaw.in/feed",
    "barandbench": "https://www.barandbench.com/feed",
}

HIGH_SCORE_KEYWORDS: list[str] = [
    "murder",
    "rape",
    "scam",
    "CBI",
    "fraud",
    "arrested",
    "conviction",
    "Supreme Court",
    "High Court",
    "sentenced",
]

CRIME_KEYWORDS: list[str] = [
    "murder",
    "rape",
    "scam",
    "fraud",
    "arrested",
    "conviction",
    "sentenced",
    "crime",
    "criminal",
    "police",
    "court",
    "accused",
    "victim",
    "assault",
    "robbery",
    "theft",
    "kidnap",
    "abduction",
    "extortion",
    "corruption",
    "bribery",
    "trafficking",
    "drug",
    "narcotics",
    "terror",
    "blast",
    "attack",
    "shooting",
    "stabbing",
    "killing",
    "dead",
    "death",
    "FIR",
    "chargesheet",
    "bail",
    "verdict",
    "acquittal",
    "CBI",
    "ED",
    "NIA",
    "IPC",
]

_SOURCE_QUALITY: dict[str, float] = {
    "livelaw": 0.10,
    "the_wire": 0.10,
    "indian_express": 0.10,
    "barandbench": 0.08,
    "toi": 0.05,
    "ndtv": 0.05,
    "the_hindu": 0.05,
    "india_today": 0.03,
    "hindustan_times": 0.03,
    "scroll": 0.03,
}

_INDIAN_KEYWORDS: list[str] = ["India", "Delhi", "Mumbai", "police", "IPC"]


def _article_text(article: dict) -> str:
    parts = [
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content", ""),
    ]
    return " ".join(p for p in parts if p)


def _published_dt(article: dict) -> Optional[datetime]:
    ts = article.get("published_parsed") or article.get("updated_parsed")
    if ts is None:
        return None
    try:
        return datetime(*ts[:6], tzinfo=timezone.utc)
    except Exception:
        return None


class RSSMonitor:
    def fetch_all(self) -> list[dict]:
        results: list[dict] = []
        for source, url in RSS_FEEDS.items():
            logger.info(f"Fetching feed: {source} — {url}")
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    entry_dict = dict(entry)
                    entry_dict["_source"] = source
                    entry_dict["content"] = (
                        entry_dict.get("summary", "")
                        if "content" not in entry_dict
                        else entry_dict["content"][0].get("value", "")
                        if isinstance(entry_dict.get("content"), list)
                        else entry_dict.get("content", "")
                    )
                    results.append(entry_dict)
                self._save_raw(source, [dict(e) for e in feed.entries])
            except Exception as exc:
                logger.error(f"Failed fetching {source}: {exc}")
            time.sleep(2)
        logger.info(f"Total raw articles fetched: {len(results)}")
        return results

    def _save_raw(self, source: str, entries: list[dict]) -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = Path("data/news")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{source}_{date_str}.json"
        safe_entries: list[dict] = []
        for e in entries:
            safe: dict = {}
            for k, v in e.items():
                try:
                    json.dumps(v)
                    safe[k] = v
                except (TypeError, ValueError):
                    safe[k] = str(v)
            safe_entries.append(safe)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(safe_entries, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved raw feed: {out_path}")
        except Exception as exc:
            logger.warning(f"Could not save raw feed for {source}: {exc}")

    def score_article(self, article: dict) -> float:
        text = _article_text(article)
        text_lower = text.lower()
        score = 0.0

        for kw in HIGH_SCORE_KEYWORDS:
            if kw.lower() in text_lower:
                score += 0.15
        score = min(score, 0.60)

        for kw in _INDIAN_KEYWORDS:
            if kw.lower() in text_lower:
                score += 0.05
        score = min(score, 0.85)

        source = article.get("_source", "")
        score += _SOURCE_QUALITY.get(source, 0.0)
        score = min(score, 0.95)

        pub_dt = _published_dt(article)
        if pub_dt is not None:
            age = datetime.now(timezone.utc) - pub_dt
            if age > timedelta(days=7):
                score *= 0.5

        return round(min(score, 1.0), 4)

    def is_crime_article(self, article: dict) -> bool:
        text = _article_text(article).lower()
        return any(kw.lower() in text for kw in CRIME_KEYWORDS)

    def dedup(self, articles: list[dict]) -> list[dict]:
        seen_urls: set[str] = set()
        seen_title_words: list[set[str]] = []
        unique: list[dict] = []

        for article in articles:
            url: str = article.get("link", "") or article.get("url", "") or ""
            if url and url in seen_urls:
                continue

            title: str = article.get("title", "")
            title_words = set(title.lower().split())

            duplicate = False
            if title_words:
                for existing_words in seen_title_words:
                    if not existing_words:
                        continue
                    overlap = len(title_words & existing_words) / max(
                        len(title_words), len(existing_words)
                    )
                    if overlap > 0.70:
                        duplicate = True
                        break

            if duplicate:
                continue

            if url:
                seen_urls.add(url)
            seen_title_words.append(title_words)
            unique.append(article)

        logger.info(f"Dedup: {len(articles)} → {len(unique)} articles")
        return unique

    def run(self, db_session) -> int:
        raw = self.fetch_all()
        crime_only = [a for a in raw if self.is_crime_article(a)]
        logger.info(f"Crime articles after filter: {len(crime_only)}")

        deduped = self.dedup(crime_only)

        new_count = 0
        for article in deduped:
            url: str = article.get("link", "") or article.get("url", "") or ""
            if not url:
                continue

            existing = db_session.query(Article).filter_by(url=url).first()
            if existing:
                continue

            pub_dt = _published_dt(article)
            score = self.score_article(article)

            db_article = Article(
                source=article.get("_source", "unknown"),
                title=article.get("title", ""),
                content=article.get("content", "") or article.get("summary", ""),
                url=url,
                published_at=pub_dt,
                story_score=score,
            )
            db_session.add(db_article)
            new_count += 1

        try:
            db_session.commit()
            logger.info(f"Saved {new_count} new articles to DB")
        except Exception as exc:
            db_session.rollback()
            logger.error(f"DB commit failed: {exc}")
            raise

        return new_count
