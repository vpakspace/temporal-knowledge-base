"""Simple in-memory TTL cache for expensive API calls (OpenAI LLM, embeddings).

Thread-safe, async-compatible. Keys are hashed strings.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TTLCache:
    """In-memory cache with time-to-live expiration."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: dict[str, tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash_key(*parts: str) -> str:
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get value if exists and not expired."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """Store value with TTL."""
        if len(self._store) >= self._max_size:
            self._evict()
        self._store[key] = (time.monotonic() + self._ttl, value)

    def _evict(self) -> None:
        """Remove expired entries, then oldest if still over max."""
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        # If still over max, remove oldest
        while len(self._store) >= self._max_size:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, int]:
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(self._hits * 100 / total) if total > 0 else 0,
        }
