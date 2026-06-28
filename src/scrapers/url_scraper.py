"""
Generic URL → article text extractor.
Uses httpx + BeautifulSoup. Degrades gracefully on any error.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from bs4 import BeautifulSoup
from loguru import logger

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# CSS class/id substrings that signal non-content elements
_NOISE_PATTERNS = (
    "ad", "sidebar", "nav", "menu", "footer", "header",
    "cookie", "popup", "banner", "social", "share", "related",
    "comment", "promo", "widget",
)


def scrape_url(url: str, timeout: int = 15) -> str:
    """
    Fetch URL and extract main article text body.
    Returns cleaned text string, or "" on any error.

    Strategy:
    1. httpx GET with browser-like User-Agent
    2. BeautifulSoup parse
    3. Remove: nav, header, footer, script, style, ads
       (tag name or class/id contains any _NOISE_PATTERNS token)
    4. Prefer article/main/[role=main] content if present
    5. Fall back to body text
    6. Clean: strip repeated whitespace, remove lines < 30 chars
    7. Truncate to 5000 chars max
    8. Return cleaned text

    Never raise — return "" on any exception (timeout, paywall, 403, etc.)
    """
    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Remove script/style tags first
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # Remove noisy structural tags by tag name
        for noise_tag in ["nav", "header", "footer", "aside"]:
            for tag in soup.find_all(noise_tag):
                tag.decompose()

        # Remove elements whose class or id contains noise patterns
        for tag in soup.find_all(True):
            classes = " ".join(tag.get("class") or []).lower()
            tag_id = (tag.get("id") or "").lower()
            if any(p in classes or p in tag_id for p in _NOISE_PATTERNS):
                tag.decompose()

        # Prefer semantic content containers
        content_tag = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find("body")
        )

        if content_tag is None:
            return ""

        raw_text = content_tag.get_text(separator="\n")

        # Clean: collapse whitespace, drop short lines (nav links, labels)
        lines = []
        for line in raw_text.splitlines():
            line = " ".join(line.split())  # collapse internal whitespace
            if len(line) >= 30:
                lines.append(line)

        text = "\n".join(lines)[:5000]

        if text:
            logger.debug("url_scraper: {} → {} chars", url[:60], len(text))
        return text

    except Exception as exc:
        logger.warning("url_scraper: failed {}: {}", url[:60], type(exc).__name__)
        return ""


def scrape_urls(urls: list[str], max_workers: int = 3) -> list[dict]:
    """
    Scrape multiple URLs concurrently using ThreadPoolExecutor.
    Returns list of {url, text, success} dicts.
    max_workers=3 to avoid hammering servers.
    """
    if not urls:
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(scrape_url, u): u for u in urls}
        for future in as_completed(future_to_url):
            u = future_to_url[future]
            try:
                text = future.result()
            except Exception as exc:
                logger.warning("url_scraper: scrape_urls future error {}: {}", u[:60], exc)
                text = ""
            results.append({"url": u, "text": text, "success": bool(text)})

    return results
