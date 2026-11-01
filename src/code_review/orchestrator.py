from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from code_review.agents.base import BaseAgent
from code_review.agents.registry import (
    build_active_agents,
    is_agent_enabled,
)
from code_review.analysis.ast_hasher import compute_diff_semantic_hash
from code_review.cache.base import BaseCache
from code_review.cache.keys import compute_cache_key, compute_diff_hash
from code_review.models.enums import AgentType, Severity, severity_rank
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult
from code_review.parsers.diff_parser import DiffFile, parse_diff

logger = logging.getLogger(__name__)


def default_agents(
    repo_root: Path | None = None,
    *,
    enabled_agent_ids: set[str] | list[str] | None = None,
    include_semantic: bool = False,
    include_llm: bool = False,
    llm_provider: str | None = None,
) -> list[BaseAgent]:
    return build_active_agents(
        enabled_agent_ids=enabled_agent_ids,
        repo_root=repo_root,
        llm_provider=llm_provider,
        include_semantic=include_semantic,
        include_llm=include_llm,
    )


def default_dedup_key(finding: Finding) -> tuple[str, int, str]:
    rule_or_msg = finding.rule_id if finding.rule_id else finding.message
    return (finding.file, finding.line, rule_or_msg)


def deduplicate_findings(
    findings: list[Finding],
    *,
    key_func: Callable[[Finding], Any] | None = None,
) -> list[Finding]:
    if not findings:
        return []

    extractor = key_func or default_dedup_key
    seen: dict[Any, Finding] = {}

    for finding in findings:
        key = extractor(finding)
        if key not in seen:
            seen[key] = finding
            continue

        existing = seen[key]
        existing_rank = severity_rank(existing.severity)
        new_rank = severity_rank(finding.severity)

        if new_rank > existing_rank:
            seen[key] = finding
        elif new_rank == existing_rank:
            if not existing.suggestion and finding.suggestion:
                seen[key] = finding

    return list(seen.values())


def sort_findings(
    findings: list[Finding],
    *,
    reverse: bool = True,
) -> list[Finding]:
    if not findings:
        return []

    def sort_key(f: Finding) -> tuple[int, str, int]:
        rank = severity_rank(f.severity)
        effective_rank = -rank if reverse else rank
        return (effective_rank, f.file, f.line)

    return sorted(findings, key=sort_key)


class ReviewOrchestrator:
    def __init__(
        self,
        agents: list[BaseAgent] | None = None,
        *,
        enabled_agent_ids: set[str] | list[str] | None = None,
        include_semantic: bool = False,
        include_llm: bool = False,
        llm_provider: str | None = None,
        parallel: bool = False,
        max_workers: int | None = None,
        deduplicate: bool = True,
        min_severity: Severity | None = None,
        cache: BaseCache | None = None,
        use_cache: bool = True,
        use_semantic_hash: bool = False,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self._enabled_agent_ids: set[str] | None = (
            {str(a).lower().strip() for a in enabled_agent_ids}
            if enabled_agent_ids is not None
            else None
        )

        if agents is None:
            self._agents: list[BaseAgent] = default_agents(
                enabled_agent_ids=self._enabled_agent_ids,
                include_semantic=include_semantic,
                include_llm=include_llm,
                llm_provider=llm_provider,
            )
        else:
            if self._enabled_agent_ids is not None:
                self._agents = [a for a in agents if self.is_agent_enabled(a)]
            else:
                self._agents = list(agents)

        self._parallel = parallel
        self._max_workers = max_workers
        self._deduplicate = deduplicate
        self._min_severity = min_severity
        self._cache = cache
        self._use_cache = use_cache
        self._use_semantic_hash = use_semantic_hash
        self._progress_callback = progress_callback
        self._last_errors: dict[str, Exception] = {}

    def is_agent_enabled(self, agent: BaseAgent) -> bool:
        """Verify whether an agent is allowed under active configuration snapshot."""
        return is_agent_enabled(agent, self._enabled_agent_ids)

    @property
    def enabled_agent_ids(self) -> set[str] | None:
        """Return a copy of the enabled agent IDs snapshot for this orchestrator instance."""
        return set(self._enabled_agent_ids) if self._enabled_agent_ids is not None else None

    @property
    def agents(self) -> list[BaseAgent]:
        return [a for a in self._agents if self.is_agent_enabled(a)]

    @property
    def active_agents(self) -> list[BaseAgent]:
        """Alias for active/enabled agents on this orchestrator instance."""
        return self.agents

    @property
    def parallel(self) -> bool:
        return self._parallel

    @property
    def cache(self) -> BaseCache | None:
        return self._cache

    @property
    def use_cache(self) -> bool:
        return self._use_cache

    @property
    def last_errors(self) -> dict[str, Exception]:
        return dict(self._last_errors)

    def register_agent(self, agent: BaseAgent) -> None:
        if self._enabled_agent_ids is not None and not self.is_agent_enabled(agent):
            logger.warning(
                "Cannot register agent '%s': agent is excluded/disabled by configuration.",
                agent.name,
            )
            return
        if agent not in self._agents:
            self._agents.append(agent)
            logger.debug("Registered agent: %s", agent.name)

    def unregister_agent(
        self,
        agent_identifier: AgentType | type[BaseAgent] | str,
    ) -> bool:
        for i, agent in enumerate(self._agents):
            match = False
            if isinstance(agent_identifier, AgentType):
                match = agent.agent_type == agent_identifier
            elif isinstance(agent_identifier, type) and issubclass(agent_identifier, BaseAgent):
                match = isinstance(agent, agent_identifier)
            elif isinstance(agent_identifier, str):
                match = agent.name.lower() == agent_identifier.lower()

            if match:
                removed = self._agents.pop(i)
                logger.debug("Unregistered agent: %s", removed.name)
                return True

        return False

    def get_agent(
        self,
        agent_identifier: AgentType | type[BaseAgent] | str,
    ) -> BaseAgent | None:
        for agent in self._agents:
            if isinstance(agent_identifier, AgentType) and agent.agent_type == agent_identifier:
                return agent
            if isinstance(agent_identifier, type) and issubclass(agent_identifier, BaseAgent):
                if isinstance(agent, agent_identifier):
                    return agent
            if (
                isinstance(agent_identifier, str)
                and agent.name.lower() == agent_identifier.lower()
            ):
                return agent
        return None

    def _compute_cache_key(
        self,
        raw_diff: str | None,
        diff_files: list[DiffFile],
        agents: list[BaseAgent],
        threshold: Severity | None,
        commit_sha: str | None = None,
    ) -> str:
        diff_h = compute_diff_hash(raw_diff or "")
        sem_h = (
            compute_diff_semantic_hash(diff_files, fallback_raw_diff=raw_diff or "")
            if self._use_semantic_hash
            else None
        )
        agent_names = [a.name for a in agents]
        sev_str = threshold.value if threshold else None
        return compute_cache_key(
            diff_h,
            commit_sha=commit_sha,
            agents=agent_names,
            min_severity=sev_str,
            semantic_hash=sem_h,
        )

    def review_diff(
        self,
        raw_diff: str,
        *,
        agents: list[BaseAgent] | None = None,
        parallel: bool | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
    ) -> ReviewResult:
        diff_files = parse_diff(raw_diff)
        return self.review_files(
            diff_files,
            raw_diff=raw_diff,
            agents=agents,
            parallel=parallel,
            deduplicate=deduplicate,
            min_severity=min_severity,
            bypass_cache=bypass_cache,
            commit_sha=commit_sha,
        )

    def review_files(
        self,
        diff_files: list[DiffFile],
        *,
        raw_diff: str | None = None,
        agents: list[BaseAgent] | None = None,
        parallel: bool | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
    ) -> ReviewResult:
        active_agents = (
            [a for a in self._agents if self.is_agent_enabled(a)]
            if agents is None
            else [a for a in agents if self.is_agent_enabled(a)]
        )
        is_parallel = self._parallel if parallel is None else parallel
        should_dedup = self._deduplicate if deduplicate is None else deduplicate
        threshold = self._min_severity if min_severity is None else min_severity

        self._last_errors.clear()
        start_time = time.perf_counter()

        if not active_agents:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ReviewResult(
                findings=[],
                files_reviewed=len(diff_files),
                review_time_ms=elapsed_ms,
                cached=False,
            )

        cache_key: str | None = None
        if self._cache is not None and self._use_cache and not bypass_cache:
            cache_key = self._compute_cache_key(
                raw_diff, diff_files, active_agents, threshold, commit_sha
            )
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        if is_parallel and len(active_agents) > 1:
            raw_findings, errors = self._run_parallel(active_agents, diff_files)
        else:
            raw_findings, errors = self._run_sequential(active_agents, diff_files)

        self._last_errors.update(errors)

        if threshold is not None:
            min_rank = severity_rank(threshold)
            raw_findings = [f for f in raw_findings if severity_rank(f.severity) >= min_rank]

        processed_findings = deduplicate_findings(raw_findings) if should_dedup else raw_findings

        final_findings = sort_findings(processed_findings, reverse=True)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        result = ReviewResult(
            findings=final_findings,
            files_reviewed=len(diff_files),
            review_time_ms=elapsed_ms,
            cached=False,
        )

        if self._cache is not None and self._use_cache and cache_key is not None:
            self._cache.set(cache_key, result)

        return result

    def review(
        self,
        target: str | list[DiffFile],
        *,
        agents: list[BaseAgent] | None = None,
        parallel: bool | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
    ) -> ReviewResult:
        if isinstance(target, str):
            return self.review_diff(
                target,
                agents=agents,
                parallel=parallel,
                deduplicate=deduplicate,
                min_severity=min_severity,
                bypass_cache=bypass_cache,
                commit_sha=commit_sha,
            )
        if isinstance(target, list):
            return self.review_files(
                target,
                agents=agents,
                parallel=parallel,
                deduplicate=deduplicate,
                min_severity=min_severity,
                bypass_cache=bypass_cache,
                commit_sha=commit_sha,
            )
        raise TypeError(
            f"Review target must be str (raw diff) or list[DiffFile], got {type(target).__name__}"
        )

    async def review_files_async(
        self,
        diff_files: list[DiffFile],
        *,
        raw_diff: str | None = None,
        agents: list[BaseAgent] | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
        max_concurrency: int | None = None,
    ) -> ReviewResult:
        active_agents = (
            [a for a in self._agents if self.is_agent_enabled(a)]
            if agents is None
            else [a for a in agents if self.is_agent_enabled(a)]
        )
        should_dedup = self._deduplicate if deduplicate is None else deduplicate
        threshold = self._min_severity if min_severity is None else min_severity

        self._last_errors.clear()
        start_time = time.perf_counter()

        if not active_agents:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ReviewResult(
                findings=[],
                files_reviewed=len(diff_files),
                review_time_ms=elapsed_ms,
                cached=False,
            )

        cache_key: str | None = None
        if self._cache is not None and self._use_cache and not bypass_cache:
            cache_key = self._compute_cache_key(
                raw_diff, diff_files, active_agents, threshold, commit_sha
            )
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        raw_findings, errors = await self._run_async(
            active_agents, diff_files, max_concurrency=max_concurrency
        )
        self._last_errors.update(errors)

        if threshold is not None:
            min_rank = severity_rank(threshold)
            raw_findings = [f for f in raw_findings if severity_rank(f.severity) >= min_rank]

        processed_findings = deduplicate_findings(raw_findings) if should_dedup else raw_findings

        final_findings = sort_findings(processed_findings, reverse=True)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        result = ReviewResult(
            findings=final_findings,
            files_reviewed=len(diff_files),
            review_time_ms=elapsed_ms,
            cached=False,
        )

        if self._cache is not None and self._use_cache and cache_key is not None:
            self._cache.set(cache_key, result)

        return result

    async def review_diff_async(
        self,
        raw_diff: str,
        *,
        agents: list[BaseAgent] | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
        max_concurrency: int | None = None,
    ) -> ReviewResult:
        diff_files = parse_diff(raw_diff)
        return await self.review_files_async(
            diff_files,
            raw_diff=raw_diff,
            agents=agents,
            deduplicate=deduplicate,
            min_severity=min_severity,
            bypass_cache=bypass_cache,
            commit_sha=commit_sha,
            max_concurrency=max_concurrency,
        )

    async def review_async(
        self,
        target: str | list[DiffFile],
        *,
        agents: list[BaseAgent] | None = None,
        deduplicate: bool | None = None,
        min_severity: Severity | None = None,
        bypass_cache: bool = False,
        commit_sha: str | None = None,
        max_concurrency: int | None = None,
    ) -> ReviewResult:
        if isinstance(target, str):
            return await self.review_diff_async(
                target,
                agents=agents,
                deduplicate=deduplicate,
                min_severity=min_severity,
                bypass_cache=bypass_cache,
                commit_sha=commit_sha,
                max_concurrency=max_concurrency,
            )
        if isinstance(target, list):
            return await self.review_files_async(
                target,
                agents=agents,
                deduplicate=deduplicate,
                min_severity=min_severity,
                bypass_cache=bypass_cache,
                commit_sha=commit_sha,
                max_concurrency=max_concurrency,
            )
        raise TypeError(
            f"Review target must be str (raw diff) or list[DiffFile], got {type(target).__name__}"
        )

    def _run_sequential(
        self,
        agents: list[BaseAgent],
        diff_files: list[DiffFile],
    ) -> tuple[list[Finding], dict[str, Exception]]:
        findings: list[Finding] = []
        errors: dict[str, Exception] = {}

        for agent in agents:
            if not self.is_agent_enabled(agent):
                continue
            try:
                agent_findings = agent.review(diff_files)
                findings.extend(agent_findings)
            except Exception as exc:
                logger.error(
                    "Agent '%s' failed during review: %s",
                    agent.name,
                    exc,
                    exc_info=True,
                )
                errors[agent.name] = exc

        return findings, errors

    def _run_parallel(
        self,
        agents: list[BaseAgent],
        diff_files: list[DiffFile],
    ) -> tuple[list[Finding], dict[str, Exception]]:
        findings: list[Finding] = []
        errors: dict[str, Exception] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_agent = {}
            for agent in agents:
                if not self.is_agent_enabled(agent):
                    continue
                if self._progress_callback:
                    self._progress_callback(agent.name, "running")
                future_to_agent[executor.submit(agent.review, diff_files)] = agent

            for future in concurrent.futures.as_completed(future_to_agent):
                agent = future_to_agent[future]
                try:
                    agent_findings = future.result()
                    findings.extend(agent_findings)
                    if self._progress_callback:
                        self._progress_callback(agent.name, "completed")
                except Exception as exc:
                    logger.error(
                        "Agent '%s' failed during parallel review: %s",
                        agent.name,
                        exc,
                        exc_info=True,
                    )
                    errors[agent.name] = exc
                    if self._progress_callback:
                        self._progress_callback(agent.name, "failed")

        return findings, errors

    async def _run_async(
        self,
        agents: list[BaseAgent],
        diff_files: list[DiffFile],
        max_concurrency: int | None = None,
    ) -> tuple[list[Finding], dict[str, Exception]]:
        findings: list[Finding] = []
        errors: dict[str, Exception] = {}

        limit = max_concurrency or self._max_workers
        sem = asyncio.Semaphore(limit) if limit and limit > 0 else None

        async def run_single(
            agent: BaseAgent,
        ) -> tuple[str, list[Finding] | None, Exception | None]:
            if not self.is_agent_enabled(agent):
                return agent.name, [], None
            try:
                if sem is not None:
                    async with sem:
                        res = await agent.review_async(diff_files)
                else:
                    res = await agent.review_async(diff_files)
                return agent.name, res, None
            except Exception as exc:
                logger.error(
                    "Agent '%s' failed during async review: %s",
                    agent.name,
                    exc,
                    exc_info=True,
                )
                return agent.name, None, exc

        tasks = [run_single(a) for a in agents]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for name, agent_findings, exc in results:
            if exc is not None:
                errors[name] = exc
            elif agent_findings:
                findings.extend(agent_findings)

        return findings, errors
Orchestrator = ReviewOrchestrator
