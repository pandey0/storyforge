"""
CLIP-based semantic re-ranking for B-roll clips.
Degrades gracefully: if sentence-transformers is not installed, returns input order unchanged.
"""
from __future__ import annotations

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy model loading — only import / download once per process
# ---------------------------------------------------------------------------
_model = None          # SentenceTransformer instance or None
_model_tried = False   # True once we've attempted to load (avoid repeated retries)
_ST_AVAILABLE = None   # Tri-state: None = unknown, True/False = resolved


def _try_import_st() -> bool:
    global _ST_AVAILABLE
    if _ST_AVAILABLE is not None:
        return _ST_AVAILABLE
    try:
        import sentence_transformers  # noqa: F401
        _ST_AVAILABLE = True
    except ImportError:
        logger.warning(
            "clip_rerank: sentence-transformers not installed; "
            "clips will not be semantically re-ranked. "
            "Install with: pip install sentence-transformers"
        )
        _ST_AVAILABLE = False
    return _ST_AVAILABLE


def _get_model():
    """Return a loaded SentenceTransformer model, or None if unavailable."""
    global _model, _model_tried
    if _model_tried:
        return _model
    _model_tried = True

    if not _try_import_st():
        return None

    from sentence_transformers import SentenceTransformer

    # Try CLIP first (multi-modal, best for images+text), fall back to a
    # small text-only model if the CLIP download fails.
    for model_name in ("clip-ViT-B-32", "paraphrase-MiniLM-L6-v2"):
        try:
            logger.info(f"clip_rerank: loading model '{model_name}'...")
            _model = SentenceTransformer(model_name)
            logger.info(f"clip_rerank: model '{model_name}' loaded")
            return _model
        except Exception as exc:
            logger.warning(f"clip_rerank: failed to load '{model_name}': {exc}")

    logger.warning("clip_rerank: all models failed to load; re-ranking disabled")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rerank_clips(clips: list[dict], query: str) -> list[dict]:
    """
    Re-rank clips by semantic similarity of their metadata to *query*.

    If sentence-transformers is unavailable or model loading fails, clips are
    returned in their original order (no error raised).

    Each clip dict should have at least one of: 'title', 'description', 'query'.
    Falls back to clip['url'] if none of those are present.
    """
    if not clips or len(clips) <= 1:
        return clips

    model = _get_model()
    if model is None:
        return clips

    try:
        from sentence_transformers import util as st_util

        # Build a text string for each clip
        clip_texts: list[str] = []
        for clip in clips:
            parts = [
                clip.get("title", ""),
                clip.get("description", ""),
                clip.get("query", ""),
            ]
            text = " ".join(p for p in parts if p).strip()
            if not text:
                text = clip.get("url", query)
            clip_texts.append(text)

        query_emb = model.encode(query, convert_to_tensor=True)
        clip_embs = model.encode(clip_texts, convert_to_tensor=True)
        scores = st_util.cos_sim(query_emb, clip_embs)[0]  # shape (N,)

        indexed = sorted(
            enumerate(clips),
            key=lambda pair: float(scores[pair[0]]),
            reverse=True,
        )
        reranked = [clip for _, clip in indexed]
        logger.debug(
            f"clip_rerank: reranked {len(clips)} clips for query='{query}' "
            f"top_score={float(scores[indexed[0][0]]):.3f}"
        )
        return reranked

    except Exception as exc:
        logger.warning(f"clip_rerank: re-ranking failed ({exc}); returning original order")
        return clips
