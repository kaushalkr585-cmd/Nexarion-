from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("code_review.observability")


@dataclass
class RequestPerformanceRecord:
    request_id: str
    mode: str
    intent: str
    provider: str
    model: str
    status_code: int
    termination_reason: str  # completed | timeout | error | cancelled | disconnected
    total_ms: float
    ttft_ms: float | None = None
    generation_ms: float | None = None
    auth_db_ms: float | None = None
    memory_ms: float | None = None
    db_persist_ms: float | None = None
    token_chunks: int = 0
    retries: int = 0
    fallback_used: bool = False
    fallback_model: str | None = None
    error_code: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class PerformanceMonitor:
    """Thread-safe lightweight rolling performance monitor for LLM & SSE chat telemetry."""

    def __init__(self, max_records: int = 500) -> None:
        self._lock = threading.Lock()
        self._records: deque[RequestPerformanceRecord] = deque(maxlen=max_records)
        self._total_requests = 0
        self._total_failures = 0
        self._total_timeouts = 0
        self._total_sse_disconnects = 0
        self._total_retries = 0
        self._by_provider_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "requests": 0,
                "failures": 0,
                "timeouts": 0,
                "retries": 0,
                "fallbacks": 0,
            }
        )

    def record(self, trace: RequestPerformanceRecord) -> None:
        with self._lock:
            self._records.append(trace)
            self._total_requests += 1
            self._total_retries += max(0, int(trace.retries))

            is_timeout = trace.termination_reason == "timeout" or trace.error_code == "TIMEOUT"
            is_disconnect = trace.termination_reason in ("disconnected", "cancelled")
            is_failure = trace.termination_reason in ("error", "timeout")

            if is_failure:
                self._total_failures += 1
            if is_timeout:
                self._total_timeouts += 1
            if is_disconnect:
                self._total_sse_disconnects += 1

            pm_key = f"{trace.provider}:{trace.model}"
            bucket = self._by_provider_model[pm_key]
            bucket["requests"] += 1
            if is_failure:
                bucket["failures"] += 1
            if is_timeout:
                bucket["timeouts"] += 1
            bucket["retries"] += max(0, int(trace.retries))
            if trace.fallback_used:
                bucket["fallbacks"] += 1

        # Structured log line (never includes API keys, tokens, passwords, or prompt content)
        logger.info(
            "[PERF] req=%s mode=%s intent=%s provider=%s model=%s status=%d "
            "reason=%s ttft_ms=%s gen_ms=%s mem_ms=%s db_ms=%s total_ms=%.1f "
            "chunks=%d retries=%d fallback=%s err=%s",
            trace.request_id,
            trace.mode,
            trace.intent,
            trace.provider,
            trace.model,
            trace.status_code,
            trace.termination_reason,
            f"{trace.ttft_ms:.1f}" if trace.ttft_ms is not None else "none",
            f"{trace.generation_ms:.1f}" if trace.generation_ms is not None else "none",
            f"{trace.memory_ms:.1f}" if trace.memory_ms is not None else "0.0",
            f"{trace.db_persist_ms:.1f}" if trace.db_persist_ms is not None else "0.0",
            trace.total_ms,
            trace.token_chunks,
            trace.retries,
            trace.fallback_model if trace.fallback_used else "false",
            trace.error_code or "none",
        )

    @staticmethod
    def _percentile(sorted_vals: list[float], pct: float) -> float:
        if not sorted_vals:
            return 0.0
        if len(sorted_vals) == 1:
            return round(sorted_vals[0], 2)
        idx = (len(sorted_vals) - 1) * (pct / 100.0)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return round(sorted_vals[lo], 2)
        frac = idx - lo
        return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 2)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
            total_reqs = self._total_requests
            failures = self._total_failures
            timeouts = self._total_timeouts
            disconnects = self._total_sse_disconnects
            retries = self._total_retries
            by_pm = {k: dict(v) for k, v in self._by_provider_model.items()}

        totals = sorted(r.total_ms for r in records if r.total_ms >= 0)
        ttfts = sorted(r.ttft_ms for r in records if r.ttft_ms is not None and r.ttft_ms >= 0)
        gens = sorted(
            r.generation_ms for r in records if r.generation_ms is not None and r.generation_ms >= 0
        )

        denom = max(1, total_reqs)
        return {
            "total_requests": total_reqs,
            "window_size": len(records),
            "avg_response_ms": round(sum(totals) / len(totals), 2) if totals else 0.0,
            "median_response_ms": self._percentile(totals, 50.0),
            "p95_response_ms": self._percentile(totals, 95.0),
            "avg_ttft_ms": round(sum(ttfts) / len(ttfts), 2) if ttfts else 0.0,
            "p95_ttft_ms": self._percentile(ttfts, 95.0),
            "avg_generation_ms": round(sum(gens) / len(gens), 2) if gens else 0.0,
            "provider_failure_rate": round(failures / denom, 4),
            "timeout_rate": round(timeouts / denom, 4),
            "sse_disconnect_rate": round(disconnects / denom, 4),
            "total_retries": retries,
            "requests_by_provider_model": by_pm,
        }


_GLOBAL_MONITOR = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    return _GLOBAL_MONITOR


class StageTimer:
    """Simple monotonic timer for breaking down backend request stage latencies."""

    def __init__(self) -> None:
        self.start = time.perf_counter()
        self._marks: dict[str, float] = {}

    def mark_ms(self, stage: str, since: float | None = None) -> float:
        base = self.start if since is None else since
        elapsed = (time.perf_counter() - base) * 1000.0
        self._marks[stage] = round(elapsed, 2)
        return elapsed

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000.0, 2)
