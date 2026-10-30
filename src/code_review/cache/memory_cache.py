from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from code_review.cache.base import BaseCache, CacheEntry
from code_review.models.review import ReviewResult


class MemoryCache(BaseCache):
    def __init__(self, maxsize: int = 500, default_ttl: float | None = None) -> None:
        self._maxsize = max(1, maxsize)
        self._default_ttl = default_ttl
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> ReviewResult | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._entries[key]
                self._misses += 1
                return None

            self._entries.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1

            result = entry.review_result.model_copy(deep=True)
            result.cached = True
            return result

    def set(
        self,
        key: str,
        result: ReviewResult,
        *,
        ttl: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(
            key=key,
            review_result=result.model_copy(deep=True),
            created_at=time.time(),
            ttl=effective_ttl,
            metadata=metadata or {},
        )

        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
            elif len(self._entries) >= self._maxsize:
                self._entries.popitem(last=False)
                self._evictions += 1

            self._entries[key] = entry

    def has(self, key: str) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._entries[key]
                return False
            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def prune(self) -> int:
        now = time.time()
        pruned = 0
        with self._lock:
            expired_keys = [k for k, v in self._entries.items() if v.is_expired(now)]
            for k in expired_keys:
                del self._entries[k]
                pruned += 1
        return pruned

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            ratio = (self._hits / total) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total,
                "hit_ratio": round(ratio, 4),
                "size": len(self._entries),
                "maxsize": self._maxsize,
                "evictions": self._evictions,
            }
