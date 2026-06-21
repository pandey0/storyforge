import os
import time
from datetime import date

import requests
from bs4 import BeautifulSoup
from loguru import logger

_CBI_PRESS_URL = "https://cbi.gov.in/press-releases"
_REPORTS_DIR = "data/reports"
_CASES_DIR = "data/cases"
_HEADERS = {"User-Agent": "IndianCrimeChannel-Research/1.0"}
_REQUEST_DELAY = 2  # seconds


class CBIScraper:
    def __init__(self):
        os.makedirs(_REPORTS_DIR, exist_ok=True)
        os.makedirs(_CASES_DIR, exist_ok=True)

    def _get_cache_path(self) -> str:
        today = date.today().isoformat()
        return os.path.join(_REPORTS_DIR, f"cbi_press_{today}.html")

    def _load_cached_html(self) -> str | None:
        path = self._get_cache_path()
        if os.path.isfile(path):
            logger.info("CBIScraper: loading cached HTML from {}", path)
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        return None

    def _save_cached_html(self, html: str) -> None:
        path = self._get_cache_path()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        logger.info("CBIScraper: cached HTML saved to {}", path)

    def _fetch_html(self, url: str) -> str | None:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code != 200:
                logger.warning("CBIScraper: {} returned status {}", url, resp.status_code)
                return None
            return resp.text
        except requests.RequestException as exc:
            logger.warning("CBIScraper: request failed for {} — {}", url, exc)
            return None

    def fetch_press_releases(self, limit: int = 50) -> list[dict]:
        html = self._load_cached_html()
        if html is None:
            html = self._fetch_html(_CBI_PRESS_URL)
            if html is None:
                logger.warning("CBIScraper: CBI site unavailable, returning empty list")
                return []
            self._save_cached_html(html)

        soup = BeautifulSoup(html, "html.parser")
        releases: list[dict] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href:
                continue
            if not href.startswith("http"):
                href = "https://cbi.gov.in" + href

            title = anchor.get_text(separator=" ", strip=True)
            if not title:
                continue

            parent_text = ""
            parent = anchor.find_parent()
            if parent:
                parent_text = parent.get_text(separator=" ", strip=True)

            date_str = ""
            for sibling in anchor.find_next_siblings(string=False):
                text = sibling.get_text(strip=True)
                if text:
                    date_str = text
                    break

            releases.append({
                "title": title,
                "url": href,
                "date": date_str,
                "preview_text": parent_text[:300],
            })

            if len(releases) >= limit:
                break

        logger.info("CBIScraper: fetched {} press releases", len(releases))
        return releases

    def fetch_release_content(self, url: str) -> str:
        time.sleep(_REQUEST_DELAY)
        html = self._fetch_html(url)
        if html is None:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content")
        if main:
            return main.get_text(separator="\n", strip=True)
        return soup.get_text(separator="\n", strip=True)

    def search_case(self, case_name: str, press_releases: list[dict] = None) -> list[dict]:
        if press_releases is None:
            press_releases = self.fetch_press_releases()

        keywords = [kw.lower() for kw in case_name.split()]
        matched: list[dict] = []

        for release in press_releases:
            haystack = (release.get("title", "") + " " + release.get("preview_text", "")).lower()
            if any(kw in haystack for kw in keywords):
                content = self.fetch_release_content(release["url"])
                matched.append({**release, "content": content})

        logger.info("CBIScraper: search_case '{}' — {} matches", case_name, len(matched))
        return matched

    def save_to_file(self, release: dict, slug: str) -> str:
        case_dir = os.path.join(_CASES_DIR, slug)
        os.makedirs(case_dir, exist_ok=True)

        existing = [
            f for f in os.listdir(case_dir)
            if f.startswith("cbi_") and f.endswith(".txt")
        ]
        index = len(existing)
        filename = f"cbi_{index}.txt"
        path = os.path.join(case_dir, filename)

        lines = []
        for key in ("title", "url", "date", "preview_text", "content"):
            val = release.get(key, "")
            if val:
                lines.append(f"{key.upper()}:\n{val}\n")

        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        logger.info("CBIScraper: saved release to {}", path)
        return path
