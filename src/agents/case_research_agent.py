from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.db.channel_profile import get_profile_for_case
from src.db.models import Case, CaseResearch
from src.db.session import get_session
from src.pipeline.state import CaseState

_ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("PDF extraction failed for {}: {}", path.name, exc)
        return ""


def _extract_image_text(path: Path) -> str:
    """Use Gemini vision to OCR / describe image content."""
    import os
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return ""
    try:
        import PIL.Image
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        img = PIL.Image.open(str(path))
        response = model.generate_content(
            [
                "Extract and transcribe all text visible in this image. "
                "If it is a photo rather than a document, describe what you see in detail. "
                "This is for documentary research.",
                img,
            ],
            generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=2000),
        )
        return response.text or ""
    except Exception as exc:
        logger.warning("Image extraction failed for {}: {}", path.name, exc)
        return ""


class CaseResearchAgent:
    """
    Reads user-uploaded research files from data/cases/{slug}/uploads/,
    extracts text (PDF / image / plain text), and uses Gemini to synthesize
    a structured research.json. No external scraping.
    """

    def run(self, slug: str) -> CaseState:
        get_profile_for_case(slug)  # validates profile exists

        with get_session() as session:
            case: Optional[Case] = session.query(Case).filter(Case.slug == slug).first()
            if case is None:
                raise ValueError(f"Case not found for slug={slug!r}")

            case.status = "research"
            session.commit()
            logger.info("run: slug={} case={!r} → status=research", slug, case.name)

            uploads = self._load_uploads(slug)

            if not uploads:
                logger.warning(
                    "No uploaded files found for slug={!r} — "
                    "upload files to data/cases/{}/uploads/ before running research",
                    slug, slug,
                )

            try:
                synthesized = self._synthesize_summary(case, uploads)
            except Exception as exc:
                logger.error("_synthesize_summary failed: {}", exc)
                synthesized = {}

            research: dict = {
                "case_slug": slug,
                "case_name": case.name,
                "researched_at": datetime.utcnow().isoformat(),
                "sources": {
                    "uploads": uploads,
                    # Schema-compat stubs (previously populated by external scrapers)
                    "general_web": [],
                    "hindi_news": [],
                    "indian_kanoon": [],
                    "news_archive": [],
                    "wikipedia": {},
                    "cbi_press": [],
                },
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
            self._update_db(case, uploads, session)

            case.status = "scripting"
            session.commit()

            logger.info("Research complete: {} uploaded docs | case={}", len(uploads), slug)

            state = CaseState.from_db_case(case)
            state.research_path = research_path
            return state

    def _load_uploads(self, slug: str) -> list[dict]:
        uploads_dir = Path(f"data/cases/{slug}/uploads")
        if not uploads_dir.exists():
            return []

        docs = []
        for path in sorted(uploads_dir.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in _ALLOWED_SUFFIXES:
                continue

            if suffix == ".pdf":
                text = _extract_pdf_text(path)
                doc_type = "pdf"
            elif suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                text = _extract_image_text(path)
                doc_type = "image"
            else:
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    text = ""
                doc_type = "text"

            if text.strip():
                docs.append({"filename": path.name, "type": doc_type, "text": text.strip()})
                logger.info("Loaded upload: {} ({}) {} chars", path.name, doc_type, len(text))

        return docs

    def _synthesize_summary(self, case: Case, uploads: list[dict]) -> dict:
        import os
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set — skipping research synthesis")
            return {}
        if not uploads:
            return {}

        combined = "\n\n---\n\n".join(
            f"[{doc['filename']}]\n{doc['text'][:4000]}" for doc in uploads
        )[:20000]

        prompt = (
            f"You are building a structured research summary for a documentary "
            f"about: {case.name!r}. The subject can be ANYTHING — a crime case, "
            f"a historical event, a biography — do not assume it is a crime.\n\n"
            "Read the uploaded research documents below and extract ONLY what "
            "they actually contain. Do not invent or guess facts the documents "
            "do not support. If content is thin, return short or empty values.\n\n"
            "Respond with ONLY a JSON object, no markdown fences:\n"
            '  "subject": one-sentence description of who/what this is about\n'
            '  "year": the year this happened as an integer, or null\n'
            '  "location": where this happened, or ""\n'
            '  "key_entities": list of {"name": str, "role": str}\n'
            '  "key_facts": list of short factual strings from the documents\n'
            '  "outcome": how this concluded/resolved, or ""\n\n'
            f"UPLOADED DOCUMENTS:\n{combined}"
        )

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.2, max_output_tokens=3000),
            )
            text = (response.text or "").strip()
        except Exception as exc:
            logger.error("research synthesis Gemini call failed: {}", exc)
            return {}

        cleaned = re.sub(r"^```(?:json)?\s*", "", text)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as exc:
            logger.error("research synthesis non-JSON: {} | text={!r}", exc, text[:300])
            return {}

    def _save_research(self, slug: str, research: dict) -> str:
        case_dir = Path("data/cases") / slug
        case_dir.mkdir(parents=True, exist_ok=True)
        research_path = case_dir / "research.json"
        research_path.write_text(json.dumps(research, indent=2, default=str), encoding="utf-8")
        logger.info("_save_research: saved → {}", research_path)
        return str(research_path)

    def _update_db(self, case: Case, uploads: list[dict], session) -> None:
        for doc in uploads:
            row = CaseResearch(
                case_id=case.id,
                source_type="upload",
                source_url=None,
                source_name=doc.get("filename", "upload"),
                content=doc.get("text", "")[:5000],
                judgment_date=None,
            )
            session.add(row)
        session.flush()
        logger.debug("_update_db: inserted {} case_research rows", len(uploads))
