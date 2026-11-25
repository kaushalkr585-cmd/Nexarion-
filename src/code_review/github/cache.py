from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class _GitHubCacheEntry:
    value: Any
    created_at: float
    ttl: float

    def is_expired(self, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        return (current - self.created_at) >= self.ttl


class GitHubCache:
    """Thread-safe LRU + TTL cache for GitHub API responses scoped by user authorization."""

    def __init__(self, maxsize: int = 1024, default_ttl: float = 300.0) -> None:
        self._maxsize = max(16, maxsize)
        self._default_ttl = default_ttl
        self._entries: OrderedDict[str, _GitHubCacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def build_key(
        scope: str,
        operation: str,
        repo: str = "",
        ref: str = "",
        extra: Any = None,
    ) -> str:
        payload = {
            "scope": scope or "public",
            "op": operation,
            "repo": repo.lower(),
            "ref": ref,
            "extra": extra,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        entry = _GitHubCacheEntry(
            value=value,
            created_at=time.time(),
            ttl=effective_ttl,
        )
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
            elif len(self._entries) >= self._maxsize:
                self._entries.popitem(last=False)
            self._entries[key] = entry

    def invalidate_scope(self, scope: str) -> int:
        """Clear cache entries when a user disconnects or rotates authorization."""
        # Entries are SHA-256 keyed; clearing full cache on auth change guarantees zero stale private reads
        del scope
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_GLOBAL_GITHUB_CACHE = GitHubCache(maxsize=1024, default_ttl=300.0)


def get_github_cache() -> GitHubCache:
    return _GLOBAL_GITHUB_CACHE
