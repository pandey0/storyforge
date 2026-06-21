"""Simple thread-safe TTL cache for FastAPI routes."""
from __future__ import annotations

import time
from functools import wraps
from threading import Lock
from typing import Any

_store: dict[tuple, dict[str, Any]] = {}
_lock = Lock()


def ttl_cache(seconds: int = 30):
    """Decorator — caches sync function return value for `seconds`."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__qualname__, args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with _lock:
                entry = _store.get(key)
                if entry and now - entry["ts"] < seconds:
                    return entry["val"]
            result = fn(*args, **kwargs)
            with _lock:
                _store[key] = {"val": result, "ts": time.monotonic()}
            return result
        return wrapper
    return decorator


def invalidate_slug(slug: str) -> None:
    """Clear all cache entries that mention a slug."""
    with _lock:
        stale = [k for k in _store if slug in str(k)]
        for k in stale:
            del _store[k]


def invalidate_all() -> None:
    with _lock:
        _store.clear()
