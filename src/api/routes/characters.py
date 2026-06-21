from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from src.db.models import Case, CaseCharacter
from src.db.session import get_session

router = APIRouter(prefix="/characters", tags=["characters"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CharacterCreate(BaseModel):
    name: str
    role: Optional[str] = None
    notes: Optional[str] = None


class CharacterUpdate(BaseModel):
    role: Optional[str] = None
    notes: Optional[str] = None


class ImageURLBody(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _char_to_dict(row: CaseCharacter) -> dict:
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "name": row.name,
        "role": row.role,
        "notes": row.notes,
        "image_path": row.image_path,
        "image_url": row.image_url,
        "added_at": row.added_at.isoformat() if row.added_at else None,
    }


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.lower())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{slug}")
async def list_characters(slug: str):
    """List all characters for a case."""
    def _fetch():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None
            rows = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.case_id == case.id)
                .order_by(CaseCharacter.added_at)
                .all()
            )
            return [_char_to_dict(r) for r in rows]

    data = await asyncio.to_thread(_fetch)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    return data


@router.post("/{slug}", status_code=201)
async def create_character(slug: str, body: CharacterCreate):
    """Add a new character to a case."""
    def _create():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "not_found"
            existing = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.case_id == case.id, CaseCharacter.name == body.name)
                .first()
            )
            if existing:
                return None, "conflict"
            row = CaseCharacter(
                id=uuid.uuid4(),
                case_id=case.id,
                name=body.name,
                role=body.role,
                notes=body.notes,
            )
            session.add(row)
            session.flush()
            return _char_to_dict(row), None

    data, err = await asyncio.to_thread(_create)
    if err == "not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    if err == "conflict":
        raise HTTPException(status_code=409, detail=f"Character '{body.name}' already exists for '{slug}'")
    return data


@router.put("/{slug}/{char_id}")
async def update_character(slug: str, char_id: str, body: CharacterUpdate):
    """Update role or notes on an existing character."""
    def _update():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "case_not_found"
            try:
                char_uuid = uuid.UUID(char_id)
            except ValueError:
                return None, "invalid_id"
            row = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.id == char_uuid, CaseCharacter.case_id == case.id)
                .first()
            )
            if not row:
                return None, "not_found"
            if body.role is not None:
                row.role = body.role
            if body.notes is not None:
                row.notes = body.notes
            session.flush()
            return _char_to_dict(row), None

    data, err = await asyncio.to_thread(_update)
    if err == "case_not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    if err == "invalid_id":
        raise HTTPException(status_code=422, detail="Invalid character ID format")
    if err == "not_found":
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    return data


@router.delete("/{slug}/{char_id}", status_code=200)
async def delete_character(slug: str, char_id: str):
    """Delete a character record (does not delete image files)."""
    def _delete():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return "case_not_found"
            try:
                char_uuid = uuid.UUID(char_id)
            except ValueError:
                return "invalid_id"
            row = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.id == char_uuid, CaseCharacter.case_id == case.id)
                .first()
            )
            if not row:
                return "not_found"
            session.delete(row)
            return "ok"

    result = await asyncio.to_thread(_delete)
    if result == "case_not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    if result == "invalid_id":
        raise HTTPException(status_code=422, detail="Invalid character ID format")
    if result == "not_found":
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    return {"deleted": True, "id": char_id}


@router.post("/{slug}/{char_id}/image-url")
async def set_image_from_url(slug: str, char_id: str, body: ImageURLBody):
    """
    Download an image from a URL and associate it with the character.
    Saves to data/cases/{slug}/characters/{safe_name}.jpg
    """
    def _download():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "case_not_found"
            try:
                char_uuid = uuid.UUID(char_id)
            except ValueError:
                return None, "invalid_id"
            row = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.id == char_uuid, CaseCharacter.case_id == case.id)
                .first()
            )
            if not row:
                return None, "not_found"

            chars_dir = Path(f"data/cases/{slug}/characters")
            chars_dir.mkdir(parents=True, exist_ok=True)

            from urllib.parse import urlparse
            parsed = urlparse(body.url)
            ext = Path(parsed.path).suffix or ".jpg"
            safe_name = _safe_filename(row.name)
            dest = chars_dir / f"{safe_name}{ext}"

            try:
                resp = requests.get(
                    body.url, timeout=30, stream=True,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"},
                )
                resp.raise_for_status()
            except requests.HTTPError as e:
                return None, f"http_{resp.status_code}"
            except requests.RequestException as e:
                return None, f"fetch_error:{e}"

            content_type = resp.headers.get("content-type", "")
            if "text/html" in content_type:
                return None, "html_not_image"

            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)

            row.image_path = str(dest)
            row.image_url = body.url
            session.flush()
            return _char_to_dict(row), None

    data, err = await asyncio.to_thread(_download)
    if err == "case_not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    if err == "invalid_id":
        raise HTTPException(status_code=422, detail="Invalid character ID format")
    if err == "not_found":
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    if err == "html_not_image":
        raise HTTPException(status_code=422, detail="URL returned an HTML page, not an image. Use a direct image URL (right-click image → Open in new tab → copy that URL).")
    if err and err.startswith("http_"):
        code = err.split("_")[1]
        raise HTTPException(status_code=422, detail=f"Server returned HTTP {code}. The image host may block hotlinking — try downloading and re-uploading, or use a different URL.")
    if err:
        raise HTTPException(status_code=500, detail=str(err))
    return data


@router.post("/{slug}/{char_id}/image-file")
async def set_image_from_file(slug: str, char_id: str, file: UploadFile = File(...)):
    """
    Accept a multipart file upload and associate it with the character.
    Saves to data/cases/{slug}/characters/{safe_name}.{ext}
    """
    # Read upload to a temp file first (avoid blocking event loop on large files)
    contents = await file.read()

    def _save():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "case_not_found"
            try:
                char_uuid = uuid.UUID(char_id)
            except ValueError:
                return None, "invalid_id"
            row = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.id == char_uuid, CaseCharacter.case_id == case.id)
                .first()
            )
            if not row:
                return None, "not_found"

            chars_dir = Path(f"data/cases/{slug}/characters")
            chars_dir.mkdir(parents=True, exist_ok=True)

            orig_filename = file.filename or "image"
            ext = Path(orig_filename).suffix or ".jpg"
            safe_name = _safe_filename(row.name)
            dest = chars_dir / f"{safe_name}{ext}"

            with open(dest, "wb") as fh:
                fh.write(contents)

            row.image_path = str(dest)
            session.flush()
            return _char_to_dict(row), None

    data, err = await asyncio.to_thread(_save)
    if err == "case_not_found":
        raise HTTPException(status_code=404, detail=f"Case '{slug}' not found")
    if err == "invalid_id":
        raise HTTPException(status_code=422, detail="Invalid character ID format")
    if err == "not_found":
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    return data


# ---------------------------------------------------------------------------
# Wikipedia auto-image search
# ---------------------------------------------------------------------------

_WIKI_UA = "IndianCrimesBot/1.0 (hindi true-crime documentary; contact: research@example.com)"

# Article titles with these words are case/event articles, not person biographies
_CASE_TITLE_WORDS = {
    "murder", "killing", "killed", "assassination", "rape", "attack", "case", "trial",
    "incident", "massacre", "shooting", "bombing", "kidnapping", "scam", "scandal",
    "fire", "accident", "tragedy", "film", "movie", "documentary", "series",
    "हत्या", "बलात्कार", "कांड", "मामला", "घटना",
}


def _is_case_article(title: str) -> bool:
    return any(w in title.lower() for w in _CASE_TITLE_WORDS)


def _title_matches_name(title: str, name: str) -> bool:
    """Return True only if article title is clearly about this person.

    Requires all name parts (>2 chars) to appear in the title, AND the title
    must not be a case/event/film article.
    """
    if _is_case_article(title):
        return False
    tl = title.lower()
    parts = [p.lower() for p in name.split() if len(p) > 2]
    return bool(parts) and all(p in tl for p in parts)


def _rank_hit(title: str, name: str) -> int:
    tl, nl = title.lower(), name.lower()
    if tl == nl:
        return 10
    if _title_matches_name(title, name):
        return 5
    if _is_case_article(title):
        return -10
    return 1


def _google_image(name: str, context: str = "") -> tuple[str | None, str | None]:
    """Search Google Custom Search API for a face portrait.

    Requires GOOGLE_SEARCH_API_KEY (Cloud Console key with Custom Search API enabled)
    and GOOGLE_CSE_ID in env. NOT the same as GOOGLE_API_KEY (Gemini/AI Studio).
    imgType=face requests portrait/headshot images.
    Returns (image_url, source_label) or (None, None).
    """
    import os
    # Use dedicated search key — GOOGLE_API_KEY is Gemini-only (AI Studio), won't work here
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
    cse_id = os.environ.get("GOOGLE_CSE_ID", "")
    if not api_key or not cse_id:
        return None, None

    query = f"{name} {context} India photo portrait".strip()
    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "searchType": "image",
                "imgType": "face",
                "imgSize": "medium",
                "num": 5,
                "safe": "off",
            },
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if items:
            best = items[0]
            return best["link"], f"Google Images — {best.get('displayLink', '')}"
    except Exception:
        pass
    return None, None


def _wikimedia_commons_image(name: str) -> tuple[str | None, str | None]:
    """Search Wikimedia Commons File namespace for a person photo.

    Filters: image filename must contain the person's name parts,
    and the file must be an image (not PDF/document).
    Returns (image_url, source_label) or (None, None).
    """
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    name_parts = [p.lower() for p in name.split() if len(p) > 2]
    headers = {"User-Agent": _WIKI_UA}

    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": name,
            "srnamespace": "6", "format": "json", "srlimit": 10, "srprop": "",
        }, headers=headers, timeout=10)
        hits = r.json().get("query", {}).get("search", [])
    except Exception:
        return None, None

    for hit in hits:
        title = hit["title"]  # e.g. "File:Jessica_Lal.jpg"
        # Must be an image file
        suffix = Path(title).suffix.lower()
        if suffix not in IMAGE_EXTS:
            continue
        # Filename must contain ALL parts of the person's name (avoids "Jessica Watson" for "Jessica Lal")
        title_lower = title.lower()
        if not all(p in title_lower for p in name_parts):
            continue

        try:
            r2 = requests.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "titles": title, "prop": "imageinfo",
                "iiprop": "url", "iiurlwidth": 500, "format": "json",
            }, headers=headers, timeout=10)
            pages = r2.json().get("query", {}).get("pages", {})
            for page in pages.values():
                ii = (page.get("imageinfo") or [{}])[0]
                url = ii.get("thumburl") or ii.get("url")
                if url:
                    return url, f"Wikimedia Commons — {title}"
        except Exception:
            continue

    return None, None


def _wikipedia_image(name: str) -> tuple[str | None, str | None]:
    """Search Wikipedia (EN then HI) for a person's biography photo.

    Skips case/event articles. Returns (image_url, article_title) or (None, None).
    """
    for lang in ("en", "hi"):
        api = f"https://{lang}.wikipedia.org/w/api.php"
        headers = {"User-Agent": _WIKI_UA}
        try:
            r = requests.get(api, params={
                "action": "query", "list": "search",
                "srsearch": name, "format": "json", "srlimit": 8, "srprop": "",
            }, headers=headers, timeout=10)
            hits = r.json().get("query", {}).get("search", [])
        except Exception:
            continue

        ranked = sorted(hits, key=lambda h: -_rank_hit(h["title"], name))
        for hit in ranked[:5]:
            title = hit["title"]
            # Only accept articles that are clearly about this person (not cases, films, etc.)
            if not _title_matches_name(title, name):
                continue
            try:
                r2 = requests.get(api, params={
                    "action": "query", "titles": title,
                    "prop": "pageimages", "format": "json",
                    "piprop": "original|thumbnail", "pithumbsize": 600,
                }, headers=headers, timeout=10)
                pages = r2.json().get("query", {}).get("pages", {})
            except Exception:
                continue
            for page in pages.values():
                src = (
                    (page.get("original") or {}).get("source")
                    or (page.get("thumbnail") or {}).get("source")
                )
                if src:
                    return src, title
    return None, None


def _find_character_image(name: str, case_name: str = "") -> tuple[str | None, str | None]:
    """Priority: Google Custom Search → Wikimedia Commons → Wikipedia biography."""
    url, label = _google_image(name, case_name)
    if url:
        return url, label
    url, label = _wikimedia_commons_image(name)
    if url:
        return url, label
    return _wikipedia_image(name)


def _download_to_chars_dir(slug: str, row: CaseCharacter, url: str, session) -> str:
    """Download image URL into characters dir, update row in-place."""
    from urllib.parse import urlparse
    ext = Path(urlparse(url).path).suffix or ".jpg"
    # Force JPEG for Wikipedia SVG thumbnails
    if ext.lower() in (".svg", ".webp", ".png"):
        ext = ".jpg"
    chars_dir = Path(f"data/cases/{slug}/characters")
    chars_dir.mkdir(parents=True, exist_ok=True)
    dest = chars_dir / f"{_safe_filename(row.name)}{ext}"

    resp = requests.get(url, timeout=30, stream=True, headers={"User-Agent": _WIKI_UA})
    resp.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(65536):
            if chunk:
                fh.write(chunk)

    row.image_path = str(dest)
    row.image_url = url
    return str(dest)


@router.post("/{slug}/{char_id}/auto-image")
async def auto_image_one(slug: str, char_id: str):
    """Search Wikipedia for this character's photo and download it."""
    def _run():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "case_not_found"
            try:
                char_uuid = uuid.UUID(char_id)
            except ValueError:
                return None, "invalid_id"
            row = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.id == char_uuid, CaseCharacter.case_id == case.id)
                .first()
            )
            if not row:
                return None, "not_found"

            img_url, source_label = _find_character_image(row.name, case.name or "")
            if not img_url:
                return {"found": False, "name": row.name}, None

            path = _download_to_chars_dir(slug, row, img_url, session)
            session.flush()
            return {"found": True, "name": row.name, "source": source_label,
                    "image_path": path, "character": _char_to_dict(row)}, None

    data, err = await asyncio.to_thread(_run)
    if err == "case_not_found":
        raise HTTPException(404, f"Case '{slug}' not found")
    if err == "invalid_id":
        raise HTTPException(422, "Invalid character ID")
    if err == "not_found":
        raise HTTPException(404, f"Character '{char_id}' not found")
    return data


@router.post("/{slug}/auto-image-all")
async def auto_image_all(slug: str):
    """Search Wikipedia for photos of all characters that don't have images yet."""
    def _run():
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == slug).first()
            if not case:
                return None, "case_not_found"

            rows = (
                session.query(CaseCharacter)
                .filter(CaseCharacter.case_id == case.id)
                .order_by(CaseCharacter.added_at)
                .all()
            )

            results = []
            for row in rows:
                # Skip if already has an image
                if row.image_path and Path(row.image_path).exists():
                    results.append({"name": row.name, "found": None, "skipped": True})
                    continue

                img_url, source_label = _find_character_image(row.name, case.name or "")
                if not img_url:
                    results.append({"name": row.name, "found": False})
                    continue

                try:
                    _download_to_chars_dir(slug, row, img_url, session)
                    results.append({"name": row.name, "found": True, "source": source_label})
                except Exception as e:
                    results.append({"name": row.name, "found": False, "error": str(e)})

            session.flush()
            found = sum(1 for r in results if r.get("found") is True)
            return {"results": results, "found": found, "total": len(rows)}, None

    data, err = await asyncio.to_thread(_run)
    if err == "case_not_found":
        raise HTTPException(404, f"Case '{slug}' not found")
    return data
