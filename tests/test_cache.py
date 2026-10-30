from __future__ import annotations

import time
from pathlib import Path

from code_review.cache.disk_cache import DiskCache
from code_review.cache.keys import compute_cache_key, compute_diff_hash, normalize_diff_text
from code_review.cache.memory_cache import MemoryCache
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult


def _make_dummy_review(num_findings: int = 1) -> ReviewResult:
    findings = [
        Finding(
            file="src/utils.py",
            line=i + 1,
            rule_id=f"R00{i}",
            message=f"Issue {i}",
            severity=Severity.WARNING,
            category=Category.CODE_QUALITY,
            agent=AgentType.AST,
        )
        for i in range(num_findings)
    ]
    return ReviewResult(findings=findings, files_reviewed=1, review_time_ms=50)


class TestDiffHashing:
    def test_normalize_diff_text_handles_crlf(self) -> None:
        diff_crlf = "--- a/file.py\r\n+++ b/file.py\r\n@@ -1,1 +1,1 @@\r\n+x = 1  \r\n"
        diff_lf = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n+x = 1\n"
        assert normalize_diff_text(diff_crlf) == normalize_diff_text(diff_lf)

    def test_compute_diff_hash_is_deterministic(self) -> None:
        diff = "--- a/f.py\n+++ b/f.py\n+a = 10\n"
        h1 = compute_diff_hash(diff)
        h2 = compute_diff_hash(diff)
        assert len(h1) == 64
        assert h1 == h2

    def test_compute_cache_key_is_order_independent_for_agents(self) -> None:
        key1 = compute_cache_key("hash1", agents=["ruff", "ast", "bandit"], min_severity="warning")
        key2 = compute_cache_key("hash1", agents=["bandit", "ast", "ruff"], min_severity="warning")
        assert key1 == key2

    def test_compute_cache_key_changes_with_commit_sha(self) -> None:
        k_none = compute_cache_key("hash1")
        k_sha1 = compute_cache_key("hash1", commit_sha="abc1234")
        k_sha2 = compute_cache_key("hash1", commit_sha="def5678")
        assert k_none != k_sha1
        assert k_sha1 != k_sha2

    def test_compute_cache_key_includes_semantic_hash(self) -> None:
        k1 = compute_cache_key("hash1", semantic_hash="sem_aaa")
        k2 = compute_cache_key("hash1", semantic_hash="sem_bbb")
        assert k1 != k2


class TestMemoryCache:
    def test_basic_get_set(self) -> None:
        cache = MemoryCache(maxsize=10)
        review = _make_dummy_review(2)

        cache.set("key1", review)
        retrieved = cache.get("key1")

        assert retrieved is not None
        assert retrieved.total_findings == 2
        assert retrieved.cached is True

    def test_get_missing_key_returns_none(self) -> None:
        cache = MemoryCache()
        assert cache.get("nonexistent") is None
        assert cache.has("nonexistent") is False

    def test_delete_and_clear(self) -> None:
        cache = MemoryCache()
        cache.set("k1", _make_dummy_review())
        cache.set("k2", _make_dummy_review())
        assert cache.size() == 2

        assert cache.delete("k1") is True
        assert cache.has("k1") is False
        assert cache.size() == 1

        cache.clear()
        assert cache.size() == 0

    def test_lru_eviction(self) -> None:
        cache = MemoryCache(maxsize=3)
        cache.set("k1", _make_dummy_review())
        cache.set("k2", _make_dummy_review())
        cache.set("k3", _make_dummy_review())

        cache.get("k1")

        cache.set("k4", _make_dummy_review())

        assert cache.has("k1") is True
        assert cache.has("k2") is False
        assert cache.has("k3") is True
        assert cache.has("k4") is True
        assert cache.stats()["evictions"] == 1

    def test_ttl_expiration(self) -> None:
        cache = MemoryCache(default_ttl=0.05)
        cache.set("k1", _make_dummy_review())
        assert cache.has("k1") is True

        time.sleep(0.08)
        assert cache.get("k1") is None
        assert cache.has("k1") is False

    def test_prune_removes_expired(self) -> None:
        cache = MemoryCache()
        cache.set("short", _make_dummy_review(), ttl=0.02)
        cache.set("long", _make_dummy_review(), ttl=10.0)

        time.sleep(0.05)
        pruned = cache.prune()
        assert pruned == 1
        assert cache.has("short") is False
        assert cache.has("long") is True

    def test_stats_tracking(self) -> None:
        cache = MemoryCache()
        cache.set("k1", _make_dummy_review())

        cache.get("k1")
        cache.get("k1")
        cache.get("miss")

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3
        assert stats["hit_ratio"] == 0.6667


class TestDiskCache:
    def test_disk_cache_roundtrip(self, tmp_path: Path) -> None:
        cache = DiskCache(cache_dir=tmp_path / "cache")
        review = _make_dummy_review(3)

        cache.set("key123", review)
        retrieved = cache.get("key123")

        assert retrieved is not None
        assert retrieved.total_findings == 3
        assert retrieved.cached is True

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "shared_cache"
        cache1 = DiskCache(cache_dir=cache_dir)
        cache1.set("shared_key", _make_dummy_review(1))

        cache2 = DiskCache(cache_dir=cache_dir)
        res = cache2.get("shared_key")
        assert res is not None
        assert res.total_findings == 1

    def test_corrupted_file_recovery(self, tmp_path: Path) -> None:
        cache = DiskCache(cache_dir=tmp_path / "cache")
        corrupt_file = cache.cache_dir / "badkey.json"
        corrupt_file.write_text("{invalid json", encoding="utf-8")

        assert cache.get("badkey") is None

    def test_disk_ttl_expiration_and_prune(self, tmp_path: Path) -> None:
        cache = DiskCache(cache_dir=tmp_path / "cache", default_ttl=0.05)
        cache.set("expired_soon", _make_dummy_review())

        time.sleep(0.08)
        assert cache.get("expired_soon") is None

        cache.set("prune_me", _make_dummy_review(), ttl=0.02)
        time.sleep(0.05)
        pruned = cache.prune()
        assert pruned >= 1

    def test_delete_and_clear(self, tmp_path: Path) -> None:
        cache = DiskCache(cache_dir=tmp_path / "cache")
        cache.set("k1", _make_dummy_review())
        cache.set("k2", _make_dummy_review())
        assert cache.size() == 2

        assert cache.delete("k1") is True
        assert cache.has("k1") is False

        cache.clear()
        assert cache.size() == 0
