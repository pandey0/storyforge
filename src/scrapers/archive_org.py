"""
Internet Archive (archive.org) scraper for free video B-roll clips.
No API key required. Uses the IA Advanced Search API + item metadata endpoint.
"""
from __future__ import annotations

import requests
from loguru import logger

_SEARCH_URL = "https://archive.org/advancedsearch.php"
_METADATA_URL = "https://archive.org/metadata/{identifier}"
_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

# Rough estimate: 1 MB ≈ 2 seconds at 4 Mbps
_MB_TO_SECONDS = 2.0
# Skip files larger than 200 MB to avoid huge downloads
_MAX_FILE_MB = 200


def search_archive_org(
    query: str,
    duration_min: int = 5,
    max_results: int = 5,
) -> list[dict]:
    """
    Search Internet Archive for freely downloadable video clips.

    Returns a list of dicts with the same schema as BRollAgent.search_pexels():
      {id, url, duration, width, height, download_url, source}

    Uses the IA Advanced Search API (no key needed). For each result, fetches
    the item's file listing to find a usable .mp4 URL.
    """
    params = {
        "q": f"{query} mediatype:movies",
        "fl[]": "identifier,title,description,subject",
        "rows": max_results,
        "output": "json",
        "sort[]": "downloads desc",
    }

    try:
        resp = requests.get(_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"archive_org: search failed for '{query}': {exc}")
        return []

    docs = data.get("response", {}).get("docs", [])
    if not docs:
        return []

    results: list[dict] = []
    for doc in docs:
        identifier = doc.get("identifier", "")
        if not identifier:
            continue

        clip = _fetch_item_clip(identifier, doc, duration_min)
        if clip:
            results.append(clip)
        if len(results) >= max_results:
            break

    logger.info(f"archive_org: '{query}' -> {len(results)} clips")
    return results


def _fetch_item_clip(identifier: str, doc: dict, duration_min: int) -> dict | None:
    """
    Fetch metadata for one IA item and return a clip dict if a suitable .mp4 exists.
    Returns None if no usable file is found.
    """
    try:
        meta_resp = requests.get(
            _METADATA_URL.format(identifier=identifier),
            timeout=10,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
    except Exception as exc:
        logger.warning(f"archive_org: metadata fetch failed for {identifier}: {exc}")
        return None

    files = meta.get("files", [])
    mp4_files = [
        f for f in files
        if isinstance(f, dict)
        and f.get("name", "").lower().endswith(".mp4")
        and f.get("name")
    ]

    if not mp4_files:
        return None

    def file_size_mb(f: dict) -> float:
        try:
            return int(f.get("size", 0)) / (1024 * 1024)
        except (ValueError, TypeError):
            return 0.0

    # Filter by size: skip files > 200 MB to avoid huge downloads
    small_enough = [f for f in mp4_files if file_size_mb(f) <= _MAX_FILE_MB]
    if not small_enough:
        # Fall back to the smallest available
        small_enough = sorted(mp4_files, key=file_size_mb)[:1]

    # Pick the file closest to 50 MB — not a tiny stub, not a huge download
    candidate = min(small_enough, key=lambda f: abs(file_size_mb(f) - 50))

    filename = candidate["name"]
    size_mb = file_size_mb(candidate)

    # Estimate duration from size if not in metadata
    duration_s: float = 0.0
    raw_length = candidate.get("length") or meta.get("metadata", {}).get("runtime")
    if raw_length:
        try:
            duration_s = float(raw_length)
        except (ValueError, TypeError):
            pass
    if duration_s <= 0 and size_mb > 0:
        duration_s = size_mb * _MB_TO_SECONDS

    # Skip if estimated duration is below minimum
    if duration_s > 0 and duration_s < duration_min:
        return None

    title = doc.get("title", "") or meta.get("metadata", {}).get("title", "")
    description = doc.get("description", "") or meta.get("metadata", {}).get("description", "")

    return {
        "id": identifier,
        "url": f"https://archive.org/details/{identifier}",
        "duration": round(duration_s, 1),
        "width": 1280,
        "height": 720,
        "download_url": _DOWNLOAD_URL.format(identifier=identifier, filename=filename),
        "title": title,
        "description": description,
        "source": "archive_org",
    }


def search_prelinger(
    query: str,
    duration_min: int = 5,
    max_results: int = 5,
) -> list[dict]:
    """
    Search Prelinger Archives on Internet Archive -- best collection for stock footage.
    Equivalent to search_archive_org() with 'prelinger' prepended to query.
    """
    return search_archive_org(
        f"prelinger {query}",
        duration_min=duration_min,
        max_results=max_results,
    )
