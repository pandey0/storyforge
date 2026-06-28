"""
Research quality scoring and timeline extraction.
Called at end of CaseResearchAgent.run() — results added to research.json.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, int] = {
    "january": 1,  "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,    "mar": 3,
    "april": 4,    "apr": 4,
    "may": 5,
    "june": 6,     "jun": 6,
    "july": 7,     "jul": 7,
    "august": 8,   "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)

# ---------------------------------------------------------------------------
# Part A — Date extraction
# ---------------------------------------------------------------------------

# Each entry: (compiled regex, format_hint)
_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ISO / numeric: 2012-12-16, 2012/12/16
    (
        re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b"),
        "YMD",
    ),
    # Day Month Year: 16 December 2012, 16 Dec 2012
    (
        re.compile(
            rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\s+(\d{{4}})\b",
            re.IGNORECASE,
        ),
        "DMY",
    ),
    # Month Day Year: December 16, 2012
    (
        re.compile(
            rf"\b({_MONTH_NAMES})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
            re.IGNORECASE,
        ),
        "MDY",
    ),
    # Year only: "in 2012", "of 2012", "year 2012", "since 2012"
    (
        re.compile(r"\b(?:in|of|year|since)\s+(\d{4})\b", re.IGNORECASE),
        "YEAR",
    ),
]


def extract_dates_from_text(text: str) -> list[dict]:
    """
    Extract date mentions from *text* with surrounding context.

    Returns list of::

        {
            "date_str":   "YYYY-MM-DD" | "YYYY",
            "year":       int,
            "context":    str,          # ±80 chars around the match
            "confidence": "full" | "year_only",
        }

    Deduped on (date_str, context[:40]), sorted by date ascending.
    """
    if not text:
        return []

    results: list[dict] = []

    for pattern, fmt in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end].strip()

            try:
                if fmt == "YMD":
                    year  = int(match.group(1))
                    month = int(match.group(2))
                    day   = int(match.group(3))
                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        continue
                    date_str   = f"{year:04d}-{month:02d}-{day:02d}"
                    confidence = "full"

                elif fmt == "DMY":
                    day   = int(match.group(1))
                    month = _MONTH_MAP.get(match.group(2).lower(), 0)
                    year  = int(match.group(3))
                    if not month or not (1 <= day <= 31):
                        continue
                    date_str   = f"{year:04d}-{month:02d}-{day:02d}"
                    confidence = "full"

                elif fmt == "MDY":
                    month = _MONTH_MAP.get(match.group(1).lower(), 0)
                    day   = int(match.group(2))
                    year  = int(match.group(3))
                    if not month or not (1 <= day <= 31):
                        continue
                    date_str   = f"{year:04d}-{month:02d}-{day:02d}"
                    confidence = "full"

                elif fmt == "YEAR":
                    year       = int(match.group(1))
                    date_str   = str(year)
                    confidence = "year_only"

                else:
                    continue

                # Sanity-gate: reject obviously bogus years
                if not (1800 <= year <= 2100):
                    continue

                results.append(
                    {
                        "date_str":   date_str,
                        "year":       year,
                        "context":    context,
                        "confidence": confidence,
                    }
                )

            except (ValueError, IndexError):
                continue

    # Deduplicate
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in results:
        key = (r["date_str"], r["context"][:40])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return sorted(unique, key=lambda x: (x["year"], x.get("date_str", "")))


# ---------------------------------------------------------------------------
# Part B — Timeline builder
# ---------------------------------------------------------------------------


def build_timeline(research: dict) -> list[dict]:
    """
    Extract all date mentions from research sources and build a chronological
    timeline.

    Returns list of::

        {
            "date":       "YYYY-MM-DD" | "YYYY",
            "year":       int,
            "event":      str,          # context sentence
            "source":     str,          # source key name
            "confidence": "full" | "year_only",
        }

    Sorted chronologically. Deduped on (date, event[:40]). Capped at 50 events.
    """

    def _events_from_text(text: str, source: str) -> list[dict]:
        return [
            {
                "date":       e["date_str"],
                "year":       e["year"],
                "event":      e["context"],
                "source":     source,
                "confidence": e["confidence"],
            }
            for e in extract_dates_from_text(text)
        ]

    events: list[dict] = []
    sources: dict = research.get("sources") or {}

    # Wikipedia full extract
    wiki = sources.get("wikipedia") or {}
    wiki_text = wiki.get("extract_full") or wiki.get("extract_summary") or ""
    if wiki_text:
        events.extend(_events_from_text(wiki_text, "wikipedia"))

    # Indian Kanoon (headline + full_text + citation)
    for doc in (sources.get("indian_kanoon") or []):
        for field in ("headline", "full_text", "citation"):
            text = doc.get(field) or ""
            if text:
                events.extend(_events_from_text(text, "indian_kanoon"))

    # General web (prefer scraped content over snippet)
    for item in (sources.get("general_web") or []):
        text = item.get("content") or item.get("snippet") or ""
        if text:
            events.extend(_events_from_text(text, "general_web"))

    # News archive (NewsAPI results — current key name in research.json)
    for item in (sources.get("news_archive") or []):
        text = (
            item.get("content")
            or item.get("snippet")
            or item.get("title")
            or ""
        )
        if text:
            events.extend(_events_from_text(text, "news_archive"))

    # Hindi news (planned separate source key — gracefully absent now)
    for item in (sources.get("hindi_news") or []):
        text = item.get("content") or item.get("snippet") or ""
        if text:
            events.extend(_events_from_text(text, "hindi_news"))

    # Sort + deduplicate
    sorted_events = sorted(
        events,
        key=lambda x: (x.get("year", 9999), x.get("date", "")),
    )

    seen: set[tuple] = set()
    unique: list[dict] = []
    for e in sorted_events:
        key = (e.get("date", ""), e.get("event", "")[:40])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique[:50]


# ---------------------------------------------------------------------------
# Part C — Quality scorer
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def score_research(research: dict) -> dict:
    """
    Score research quality 0–10 and identify content gaps.

    Returns::

        {
            "score":               int,   # 0-10
            "word_count_total":    int,
            "word_count_by_source": {
                "wikipedia":     int,
                "indian_kanoon": int,
                "general_web":   int,
                "hindi_news":    int,
                "news_archive":  int,
            },
            "sources_found":  list[str],
            "sources_empty":  list[str],
            "gaps":           list[str],
            "timeline_events": int,
        }
    """
    sources: dict = research.get("sources") or {}
    gaps: list[str] = []

    # ------------------------------------------------------------------
    # Word counts per source
    # ------------------------------------------------------------------

    # Wikipedia
    wiki = sources.get("wikipedia") or {}
    wiki_text = wiki.get("extract_full") or wiki.get("extract_summary") or ""
    wc_wikipedia = _word_count(wiki_text)

    # Indian Kanoon — sum headline + full_text + citation
    wc_ik = 0
    ik_docs = sources.get("indian_kanoon") or []
    ik_has_full_text = False
    for doc in ik_docs:
        for field in ("headline", "full_text", "citation"):
            wc_ik += _word_count(doc.get(field) or "")
        if doc.get("full_text"):
            ik_has_full_text = True

    # General web — prefer content over snippet
    wc_web = 0
    web_items = sources.get("general_web") or []
    web_scraped_count = 0
    for item in web_items:
        content = item.get("content") or ""
        snippet = item.get("snippet") or ""
        wc_web += _word_count(content or snippet)
        if len(content) > 200:
            web_scraped_count += 1

    # News archive (current key in research.json)
    wc_news_archive = 0
    for item in (sources.get("news_archive") or []):
        wc_news_archive += _word_count(
            item.get("content") or item.get("snippet") or item.get("title") or ""
        )

    # Hindi news (future separate source key)
    wc_hindi_news = 0
    for item in (sources.get("hindi_news") or []):
        wc_hindi_news += _word_count(item.get("content") or item.get("snippet") or "")

    word_count_by_source = {
        "wikipedia":     wc_wikipedia,
        "indian_kanoon": wc_ik,
        "general_web":   wc_web,
        "hindi_news":    wc_hindi_news,
        "news_archive":  wc_news_archive,
    }
    word_count_total = sum(word_count_by_source.values())

    # ------------------------------------------------------------------
    # Sources found / empty
    # ------------------------------------------------------------------

    sources_found: list[str] = []
    sources_empty: list[str] = []

    def _non_empty(key: str) -> bool:
        v = sources.get(key)
        if isinstance(v, dict):
            return bool(v)
        if isinstance(v, list):
            return len(v) > 0
        return False

    for key in ("wikipedia", "indian_kanoon", "general_web", "hindi_news", "news_archive"):
        (sources_found if _non_empty(key) else sources_empty).append(key)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    score = 0

    # Wikipedia
    if wc_wikipedia >= 500:
        score += 2
    elif wc_wikipedia > 0:
        score += 1

    # Indian Kanoon
    if ik_docs:
        score += 1
        if ik_has_full_text:
            score += 2

    # General web scraped content (max +2)
    score += min(web_scraped_count, 2)

    # Hindi news / news archive — any coverage at all
    if wc_hindi_news > 0 or wc_news_archive > 0:
        score += 1

    # Total word count bonus
    if word_count_total > 5000:
        score += 2
    elif word_count_total > 2000:
        score += 1

    # Timeline richness (timeline already attached to research dict when
    # score_research is called from run() — see wiring in case_research_agent.py)
    tl = research.get("timeline") or []
    if len(tl) > 5:
        score += 1

    score = min(score, 10)

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    if not wiki_text:
        gaps.append("No Wikipedia page found — main background source missing")

    if ik_docs and not ik_has_full_text:
        gaps.append(
            "Indian Kanoon: only headlines fetched, no full judgment text"
        )

    if web_items and web_scraped_count == 0:
        gaps.append("Web search: only snippets, article content not scraped")

    if word_count_total < 500:
        gaps.append(
            "Research critically thin — consider adding manual research before scripting"
        )
    elif word_count_total < 1000:
        gaps.append(
            "Research very thin — script will rely heavily on AI inference"
        )

    if wc_hindi_news == 0 and wc_news_archive == 0 and wc_web < 200:
        gaps.append("No Hindi-language sources found")

    return {
        "score":                score,
        "word_count_total":     word_count_total,
        "word_count_by_source": word_count_by_source,
        "sources_found":        sources_found,
        "sources_empty":        sources_empty,
        "gaps":                 gaps,
        "timeline_events":      len(tl),
    }
