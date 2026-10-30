from __future__ import annotations

import hashlib
from collections.abc import Iterable


def normalize_diff_text(diff_text: str) -> str:
    if not diff_text:
        return ""

    lines = diff_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized_lines = [line.rstrip() for line in lines]
    return "\n".join(normalized_lines).strip()


def compute_diff_hash(diff_text: str) -> str:
    normalized = normalize_diff_text(diff_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_cache_key(
    diff_hash: str,
    *,
    commit_sha: str | None = None,
    agents: Iterable[str] | None = None,
    min_severity: str | None = None,
    semantic_hash: str | None = None,
) -> str:
    sorted_agents = sorted(a.lower().strip() for a in (agents or []))
    agents_str = ",".join(sorted_agents)
    sha_str = (commit_sha or "").strip().lower()
    sev_str = (min_severity or "").strip().lower()
    sem_str = (semantic_hash or "").strip().lower()

    payload = f"diff={diff_hash}|sha={sha_str}|agents={agents_str}|sev={sev_str}|sem={sem_str}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
