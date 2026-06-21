from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from slugify import slugify

from src.db.models import Case, CaseResearch
from src.db.session import get_session
from src.pipeline.state import CaseState
from src.scrapers.google_search import GoogleSearchClient
from src.scrapers.indian_kanoon import IndianKanoonClient
from src.scrapers.news_api import NewsAPIClient

_WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_WIKI_EXTRACT_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts&explaintext=1&format=json"
)


class CaseResearchAgent:
    def __init__(self) -> None:
        self._ik_client = IndianKanoonClient()
        self._news_client = NewsAPIClient()
        self._web_client = GoogleSearchClient()
        self._http = httpx.Client(
            timeout=30,
            headers={"User-Agent": "IndianCrimeChannel-Research/1.0"},
        )

    def run(self, slug: str) -> CaseState:
        with get_session() as session:
            case: Optional[Case] = (
                session.query(Case).filter(Case.slug == slug).first()
            )
            if case is None:
                raise ValueError(f"Case not found for slug={slug!r}")

            case.status = "research"
            session.commit()
            logger.info("run: slug={} case={!r} → status=research", slug, case.name)

            ik_results: list[dict] = []
            news_results: list[dict] = []
            web_results: list[dict] = []
            wiki_data: Optional[dict] = None

            try:
                ik_results = self._search_indian_kanoon(case.name, slug)
            except Exception as exc:
                logger.error("_search_indian_kanoon failed: {}", exc)

            try:
                news_results = self._search_news_archive(case.name)
            except Exception as exc:
                logger.error("_search_news_archive failed: {}", exc)

            try:
                web_results = self._search_web(case.name)
            except Exception as exc:
                logger.error("_search_web failed: {}", exc)

            try:
                wiki_data = self._fetch_wikipedia(case.name)
            except Exception as exc:
                logger.error("_fetch_wikipedia failed: {}", exc)

            if not ik_results and not news_results and not web_results and wiki_data is None:
                logger.warning(
                    "All external sources returned empty for slug={!r} — proceeding with case DB info only",
                    slug,
                )

            try:
                synthesized = self._synthesize_summary(case, ik_results, news_results, web_results, wiki_data)
            except Exception as exc:
                logger.error("_synthesize_summary failed: {}", exc)
                synthesized = {}

            research: dict = {
                "case_slug": slug,
                "case_name": case.name,
                "researched_at": datetime.utcnow().isoformat(),
                "sources": {
                    "indian_kanoon": ik_results,
                    "news_archive": news_results,
                    # General web search (Google Custom Search) — niche-agnostic,
                    # unlike indian_kanoon (India court judgments only).
                    "general_web": web_results,
                    "wikipedia": wiki_data or {},
                    "cbi_press": [],
                },
                # Generic across any subject (true crime, mythology, history,
                # etc.) — no crime-specific field names. See docs/SHORTS_FLOW.md
                # and CLAUDE.md "Niche Is Data Too". key_entities/key_facts/
                # outcome are filled by _synthesize_summary reading the raw
                # scraped sources above, not hand-typed at case creation.
                "summary": {
                    "subject": synthesized.get("subject") or case.subject_name or case.name or "",
                    "year": synthesized.get("year") or case.year_of_crime,
                    "location": synthesized.get("location") or case.location or "",
                    "key_entities": synthesized.get("key_entities") or [],
                    "key_facts": synthesized.get("key_facts") or [],
                    "outcome": synthesized.get("outcome") or "",
                },
            }

            research_path = self._save_research(slug, research)

            all_items: list[dict] = []
            for item in ik_results:
                all_items.append({"source_type": "indian_kanoon", **item})
            for item in news_results:
                all_items.append({"source_type": "news_archive", **item})
            for item in web_results:
                all_items.append({"source_type": "general_web", **item})
            if wiki_data:
                all_items.append({"source_type": "wikipedia", **wiki_data})

            self._update_db(case, all_items, session)

            case.status = "scripting"
            session.commit()

            logger.info(
                "Research complete: {} Indian Kanoon, {} news, {} web, wikipedia={}",
                len(ik_results),
                len(news_results),
                len(web_results),
                wiki_data is not None,
            )

            state = CaseState.from_db_case(case)
            state.research_path = research_path
            return state

    def _synthesize_summary(
        self,
        case: Case,
        ik_results: list[dict],
        news_results: list[dict],
        web_results: list[dict],
        wiki_data: Optional[dict],
    ) -> dict:
        """
        Read the raw scraped sources and produce an actual structured
        understanding of the case — subject/key_entities/key_facts/outcome —
        instead of leaving those fields as empty templates. Strictly grounded
        in the scraped text; told explicitly not to invent facts the sources
        don't contain. Generic across any subject, not just crime.
        """
        import os

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set — skipping research synthesis")
            return {}

        wiki_text = ""
        if wiki_data:
            wiki_text = wiki_data.get("extract_full") or wiki_data.get("extract_summary") or ""

        if not ik_results and not news_results and not web_results and not wiki_text:
            return {}

        sources_text = json.dumps(
            {
                "indian_kanoon": ik_results[:10],
                "news_archive": news_results[:10],
                "general_web": web_results[:10],
                "wikipedia_extract": wiki_text[:6000],
            },
            ensure_ascii=False,
            indent=2,
        )

        prompt = (
            f"You are building a structured research summary for a documentary "
            f"about: {case.name!r}. The subject can be ANYTHING — a crime case, "
            f"a historical event, a mythological story, a biography — do not "
            f"assume it's a crime.\n\n"
            "Read the raw sources below and extract ONLY what they actually "
            "contain. Do not invent or guess facts the sources don't support. "
            "If the sources are thin or empty, return short/empty values rather "
            "than fabricating content.\n\n"
            "Respond with ONLY a JSON object, no markdown fences, with exactly "
            "these keys:\n"
            '  "subject": one-sentence description of who/what this case is about\n'
            '  "year": the year this happened, as an integer, or null if unclear\n'
            '  "location": where this happened, or "" if unclear\n'
            '  "key_entities": a list of {"name": str, "role": str} for the '
            "real people/figures/entities the sources mention — role is free "
            "text describing their actual involvement (e.g. \"victim\", "
            "\"accused\", \"deity\", \"witness\", \"investigating officer\" — "
            "whatever fits this specific subject)\n"
            '  "key_facts": a list of short factual strings drawn directly '
            "from the sources\n"
            '  "outcome": how this concluded/resolved (verdict, ending, '
            'resolution — whatever "outcome" means for this subject), or "" '
            "if the sources don't say\n\n"
            f"RAW SOURCES:\n{sources_text}"
        )

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    # gemini-2.5-flash burns an uncontrolled amount of tokens
                    # on internal "thinking" before any visible output —
                    # learned the hard way this session that under ~1500 risks
                    # silent truncation. This prompt + sources is meatier, so
                    # give it real headroom.
                    max_output_tokens=3000,
                ),
            )
            text = (response.text or "").strip()
        except Exception as exc:
            logger.error("research synthesis Gemini call failed: {}", exc)
            return {}

        cleaned = re.sub(r"^```(?:json)?\s*", "", text)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("research synthesis returned non-JSON: {} | text={!r}", exc, text[:500])
            return {}

        if not isinstance(data, dict):
            logger.error("research synthesis returned non-dict JSON: {!r}", data)
            return {}

        return data

    def _search_indian_kanoon(self, case_name: str, slug: str) -> list[dict]:
        logger.info("_search_indian_kanoon: case_name={!r}", case_name)
        results = self._ik_client.search_case(case_name, max_results=10)
        logger.debug("_search_indian_kanoon: {} results", len(results))
        return results

    def _search_news_archive(self, case_name: str) -> list[dict]:
        logger.info("_search_news_archive: case_name={!r}", case_name)
        results = self._news_client.search_case(case_name)
        logger.debug("_search_news_archive: {} results", len(results))
        return results

    def _search_web(self, case_name: str) -> list[dict]:
        logger.info("_search_web: case_name={!r}", case_name)
        results = self._web_client.search_case(case_name, max_results=10)
        logger.debug("_search_web: {} results", len(results))
        return results

    def _fetch_wikipedia(self, case_name: str) -> Optional[dict]:
        logger.info("_fetch_wikipedia: case_name={!r}", case_name)

        def _try_wiki(title: str) -> Optional[dict]:
            encoded = title.replace(" ", "_")

            summary_url = _WIKI_SUMMARY_URL.format(title=encoded)
            resp = self._http.get(summary_url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            summary = resp.json()

            time.sleep(1)

            extract_url = _WIKI_EXTRACT_URL.format(title=encoded)
            resp2 = self._http.get(extract_url)
            resp2.raise_for_status()
            extract_data = resp2.json()

            pages = (extract_data.get("query") or {}).get("pages") or {}
            extract_text = ""
            for page_val in pages.values():
                extract_text = page_val.get("extract") or ""
                break

            return {
                "title": summary.get("title") or title,
                "description": summary.get("description") or "",
                "extract_summary": summary.get("extract") or "",
                "extract_full": extract_text,
                "page_url": summary.get("content_urls", {})
                .get("desktop", {})
                .get("page", ""),
            }

        # Try 1: direct title
        result = _try_wiki(case_name.replace(" ", "_"))
        if result:
            return result
        time.sleep(0.5)

        # Try 2: Wikipedia search API → grab first hit
        try:
            search_url = (
                "https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={case_name.replace(' ', '+')}"
                "&format=json&srlimit=3"
            )
            resp = self._http.get(search_url)
            resp.raise_for_status()
            hits = resp.json().get("query", {}).get("search", [])
            for hit in hits:
                title = hit.get("title", "")
                if title:
                    time.sleep(0.5)
                    result = _try_wiki(title)
                    if result:
                        logger.info("_fetch_wikipedia: found via search → {!r}", title)
                        return result
        except Exception as exc:
            logger.debug("_fetch_wikipedia search API failed: {}", exc)

        logger.warning("_fetch_wikipedia: no Wikipedia page found for {!r}", case_name)
        return None

    def _save_research(self, slug: str, research: dict) -> str:
        case_dir = Path("data/cases") / slug
        case_dir.mkdir(parents=True, exist_ok=True)
        research_path = case_dir / "research.json"
        research_path.write_text(
            json.dumps(research, indent=2, default=str), encoding="utf-8"
        )
        logger.info("_save_research: saved → {}", research_path)
        return str(research_path)

    def _update_db(
        self, case: Case, research_items: list[dict], session
    ) -> None:
        for item in research_items:
            source_type = item.get("source_type", "unknown")

            if source_type == "indian_kanoon":
                source_url = (
                    f"https://indiankanoon.org/doc/{item.get('docid', '')}/"
                    if item.get("docid")
                    else None
                )
                source_name = item.get("court") or item.get("title") or ""
                content = item.get("headline") or item.get("citation") or ""
                judgment_date_raw = item.get("date") or ""
                judgment_date = None
                if judgment_date_raw:
                    try:
                        judgment_date = datetime.strptime(
                            judgment_date_raw[:10], "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        pass

            elif source_type == "news_archive":
                source_url = item.get("url") or None
                source_name = item.get("source") or item.get("title") or ""
                content = item.get("content") or item.get("title") or ""
                judgment_date = None

            elif source_type == "wikipedia":
                source_url = item.get("page_url") or None
                source_name = item.get("title") or "Wikipedia"
                content = item.get("extract_full") or item.get("extract_summary") or ""
                judgment_date = None

            else:
                source_url = None
                source_name = source_type
                content = json.dumps(item, default=str)
                judgment_date = None

            row = CaseResearch(
                case_id=case.id,
                source_type=source_type,
                source_url=source_url,
                source_name=source_name,
                content=content,
                judgment_date=judgment_date,
            )
            session.add(row)

        session.flush()
        logger.debug("_update_db: inserted {} case_research rows", len(research_items))
