from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from code_review.models.review import ReviewResult


@dataclass
class CacheEntry:
    key: str
    review_result: ReviewResult
    created_at: float = field(default_factory=time.time)
    ttl: float | None = None
    hit_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, current_time: float | None = None) -> bool:
        if self.ttl is None or self.ttl <= 0:
            return False
        now = current_time if current_time is not None else time.time()
        return (now - self.created_at) > self.ttl


class BaseCache(ABC):
    @abstractmethod
    def get(self, key: str) -> ReviewResult | None:
        pass

    @abstractmethod
    def set(
        self,
        key: str,
        result: ReviewResult,
        *,
        ttl: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def has(self, key: str) -> bool:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def size(self) -> int:
        pass

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        pass
