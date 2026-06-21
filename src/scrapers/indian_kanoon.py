import os
import time
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

load_dotenv()

_BASE_URL = "https://api.indiankanoon.org/"
_CACHE_DIR = Path("data/raw_judgments")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 503)
    return False


class IndianKanoonClient:
    def __init__(self):
        self._token = os.getenv("INDIAN_KANOON_TOKEN", "")
        if not self._token:
            logger.warning("INDIAN_KANOON_TOKEN not set — IndianKanoonClient will skip API calls")
        self._headers = {
            "Authorization": f"Token {self._token}",
            "User-Agent": "IndianCrimeChannel-Research/1.0",
        }
        self._client = httpx.Client(base_url=_BASE_URL, headers=self._headers, timeout=30)

    def _rate_limit(self) -> None:
        time.sleep(1)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        self._rate_limit()
        logger.debug("IndianKanoon GET {} params={}", path, params)
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp

    def search(self, query: str, page: int = 0) -> list[dict]:
        if not self._token:
            return []
        logger.info("IndianKanoon search: '{}' page={}", query, page)
        try:
            resp = self._get("search/", params={"formInput": query, "pagenum": page})
            data = resp.json()
            docs = data.get("docs") or []
            results = []
            for d in docs:
                results.append({
                    "title": d.get("title") or "",
                    "docid": str(d.get("tid") or d.get("docid") or ""),
                    "headline": d.get("headline") or "",
                    "citation": d.get("citation") or "",
                    "court": d.get("docsource") or "",
                    "date": d.get("publishdate") or "",
                })
            return results
        except Exception as exc:
            logger.error("IndianKanoon search error: {}", exc)
            return []

    def get_document(self, docid: str) -> dict:
        if not self._token:
            return {}
        cache_path = _CACHE_DIR / f"{docid}.txt"
        if cache_path.exists():
            logger.info("IndianKanoon cache hit: {}", docid)
            text = cache_path.read_text(encoding="utf-8")
            return {"title": "", "docid": docid, "text": text, "citations": [], "court": "", "date": ""}
        logger.info("IndianKanoon get_document: {}", docid)
        try:
            resp = self._get(f"doc/{docid}/")
            data = resp.json()
            return {
                "title": data.get("title") or "",
                "docid": docid,
                "text": data.get("doc") or "",
                "citations": data.get("citedDocs") or [],
                "court": data.get("docsource") or "",
                "date": data.get("publishdate") or "",
            }
        except Exception as exc:
            logger.error("IndianKanoon get_document error docid={}: {}", docid, exc)
            return {}

    def search_case(self, case_name: str, max_results: int = 10) -> list[dict]:
        if not self._token:
            return []
        logger.info("IndianKanoon search_case: '{}'", case_name)
        results: list[dict] = []
        page = 0
        while len(results) < max_results:
            batch = self.search(case_name, page=page)
            if not batch:
                break
            results.extend(batch)
            page += 1
        return results[:max_results]

    def download_judgment(self, docid: str, save_path: str) -> str:
        if not self._token:
            logger.warning("IndianKanoon token missing — skipping download for {}", docid)
            return ""
        doc = self.get_document(docid)
        text = doc.get("text") or ""
        dest = Path(save_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        cache_dest = _CACHE_DIR / f"{docid}.txt"
        if not cache_dest.exists():
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_dest.write_text(text, encoding="utf-8")
        logger.info("IndianKanoon saved judgment {} → {}", docid, save_path)
        return save_path
