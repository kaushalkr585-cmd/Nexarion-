from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from code_review.cache.base import BaseCache
from code_review.models.review import ReviewResult

logger = logging.getLogger(__name__)


class DiskCache(BaseCache):
    def __init__(
        self,
        cache_dir: str | Path = ".cache/code_review",
        default_ttl: float | None = 86400.0,
    ) -> None:
        self.cache_dir = Path(cache_dir).resolve()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_for_key(self, key: str) -> Path:
        safe_name = "".join(c for c in key if c.isalnum() or c in ("-", "_"))
        return self.cache_dir / f"{safe_name}.json"

    def get(self, key: str) -> ReviewResult | None:
        path = self._file_for_key(key)
        if not path.is_file():
            self._misses += 1
            return None

        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)

            created_at = data.get("created_at", 0.0)
            ttl = data.get("ttl")
            if ttl is not None and ttl > 0:
                if (time.time() - created_at) > ttl:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    self._misses += 1
                    return None

            result_dict = data.get("review_result")
            if not result_dict:
                self._misses += 1
                return None

            result = ReviewResult.model_validate(result_dict)
            result.cached = True
            self._hits += 1
            return result

        except Exception as exc:
            logger.warning("Failed to read cache file %s: %s", path, exc)
            self._misses += 1
            return None

    def set(
        self,
        key: str,
        result: ReviewResult,
        *,
        ttl: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        path = self._file_for_key(key)

        payload = {
            "key": key,
            "created_at": time.time(),
            "ttl": effective_ttl,
            "metadata": metadata or {},
            "review_result": json.loads(result.model_dump_json()),
        }

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_dir,
                delete=False,
                suffix=".tmp",
            ) as tmp_file:
                json.dump(payload, tmp_file, indent=2)
                tmp_path = Path(tmp_file.name)

            os.replace(tmp_path, path)

        except Exception as exc:
            logger.error("Failed to write disk cache for key %s: %s", key, exc)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def delete(self, key: str) -> bool:
        path = self._file_for_key(key)
        if path.is_file():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    def clear(self) -> None:
        if self.cache_dir.is_dir():
            for child in self.cache_dir.glob("*.json"):
                try:
                    child.unlink()
                except OSError:
                    pass
            for tmp in self.cache_dir.glob("*.tmp"):
                try:
                    tmp.unlink()
                except OSError:
                    pass
        self._hits = 0
        self._misses = 0

    def purge_directory(self) -> None:
        if self.cache_dir.is_dir():
            shutil.rmtree(self.cache_dir, ignore_errors=True)

    def size(self) -> int:
        if not self.cache_dir.is_dir():
            return 0
        return len(list(self.cache_dir.glob("*.json")))

    def prune(self) -> int:
        if not self.cache_dir.is_dir():
            return 0

        now = time.time()
        pruned = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                created_at = data.get("created_at", 0.0)
                ttl = data.get("ttl")
                if ttl and ttl > 0 and (now - created_at) > ttl:
                    path.unlink(missing_ok=True)
                    pruned += 1
            except Exception:
                path.unlink(missing_ok=True)
                pruned += 1
        return pruned

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        ratio = (self._hits / total) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_ratio": round(ratio, 4),
            "size": self.size(),
            "cache_dir": str(self.cache_dir),
        }
