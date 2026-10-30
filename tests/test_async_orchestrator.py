from __future__ import annotations

import io
import time

import pytest

from code_review.agents.base import BaseAgent
from code_review.cache.memory_cache import MemoryCache
from code_review.cli.main import main
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.orchestrator import ReviewOrchestrator
from code_review.parsers.diff_parser import DiffFile, parse_diff

SAMPLE_DIFF = (
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,3 @@\n+x = 1\n+y = 2\n"
)


class SlowMockAgent(BaseAgent):
    def __init__(self, name: str, delay: float = 0.05, agent_type: AgentType = AgentType.AST):
        self._name = name
        self._delay = delay
        self._agent_type = agent_type
        self.call_count = 0

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    @property
    def name(self) -> str:
        return self._name

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        self.call_count += 1
        time.sleep(self._delay)
        return [
            Finding(
                file="app.py",
                line=1,
                rule_id=f"{self.name.upper()}_01",
                message=f"Finding from {self.name}",
                severity=Severity.WARNING,
                category=Category.CODE_QUALITY,
                agent=self.agent_type,
            )
        ]


class FailingMockAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.RUFF

    @property
    def name(self) -> str:
        return "failing"

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        raise RuntimeError("Crash in failing agent")


class TestAsyncOrchestrator:
    @pytest.mark.anyio
    async def test_review_diff_async_basic(self) -> None:
        agent = SlowMockAgent("test_agent", delay=0.01)
        orch = ReviewOrchestrator(agents=[agent])

        result = await orch.review_diff_async(SAMPLE_DIFF)
        assert result.total_findings == 1
        assert result.files_reviewed == 1
        assert agent.call_count == 1

    @pytest.mark.anyio
    async def test_review_async_dispatcher_types(self) -> None:
        agent = SlowMockAgent("test_agent", delay=0.01)
        orch = ReviewOrchestrator(agents=[agent])

        res_str = await orch.review_async(SAMPLE_DIFF)
        assert res_str.total_findings == 1

        parsed = parse_diff(SAMPLE_DIFF)
        res_files = await orch.review_async(parsed)
        assert res_files.total_findings == 1

        with pytest.raises(TypeError):
            await orch.review_async(12345)  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_async_parallel_speedup(self) -> None:
        delay = 0.08
        agent1 = SlowMockAgent("agent1", delay=delay, agent_type=AgentType.AST)
        agent2 = SlowMockAgent("agent2", delay=delay, agent_type=AgentType.RUFF)
        orch = ReviewOrchestrator(agents=[agent1, agent2])

        t0 = time.perf_counter()
        result = await orch.review_diff_async(SAMPLE_DIFF)
        elapsed = time.perf_counter() - t0

        assert result.total_findings == 2

        assert elapsed < (delay * 1.8)

    @pytest.mark.anyio
    async def test_async_fault_tolerance(self) -> None:
        good_agent = SlowMockAgent("good", delay=0.01)
        bad_agent = FailingMockAgent()
        orch = ReviewOrchestrator(agents=[good_agent, bad_agent])

        result = await orch.review_diff_async(SAMPLE_DIFF)
        assert result.total_findings == 1
        assert "failing" in orch.last_errors
        assert isinstance(orch.last_errors["failing"], RuntimeError)


class TestOrchestratorCaching:
    def test_cache_hit_returns_cached_result(self) -> None:
        agent = SlowMockAgent("agent1", delay=0.01)
        cache = MemoryCache()
        orch = ReviewOrchestrator(agents=[agent], cache=cache, use_cache=True)

        res1 = orch.review_diff(SAMPLE_DIFF)
        assert res1.cached is False
        assert agent.call_count == 1

        res2 = orch.review_diff(SAMPLE_DIFF)
        assert res2.cached is True
        assert res2.total_findings == res1.total_findings
        assert agent.call_count == 1

    def test_bypass_cache_flag_re_runs_agents(self) -> None:
        agent = SlowMockAgent("agent1", delay=0.01)
        cache = MemoryCache()
        orch = ReviewOrchestrator(agents=[agent], cache=cache, use_cache=True)

        orch.review_diff(SAMPLE_DIFF)
        assert agent.call_count == 1

        res = orch.review_diff(SAMPLE_DIFF, bypass_cache=True)
        assert res.cached is False
        assert agent.call_count == 2

    def test_commit_sha_separates_cache_entries(self) -> None:
        agent = SlowMockAgent("agent1", delay=0.01)
        cache = MemoryCache()
        orch = ReviewOrchestrator(agents=[agent], cache=cache)

        orch.review_diff(SAMPLE_DIFF, commit_sha="sha_v1")
        assert agent.call_count == 1

        orch.review_diff(SAMPLE_DIFF, commit_sha="sha_v2")
        assert agent.call_count == 2

    @pytest.mark.anyio
    async def test_async_review_with_cache(self) -> None:
        agent = SlowMockAgent("agent1", delay=0.01)
        cache = MemoryCache()
        orch = ReviewOrchestrator(agents=[agent], cache=cache)

        res1 = await orch.review_diff_async(SAMPLE_DIFF)
        assert res1.cached is False
        assert agent.call_count == 1

        res2 = await orch.review_diff_async(SAMPLE_DIFF)
        assert res2.cached is True
        assert agent.call_count == 1


class TestCLICacheFlags:
    def test_cli_clear_cache(self, tmp_path) -> None:
        cache_dir = tmp_path / "cli_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "test.json").write_text("{}", encoding="utf-8")

        out = io.StringIO()
        code = main(["--clear-cache", "--cache-dir", str(cache_dir)], stdout=out)
        assert code == 0
        assert "Cleared" in out.getvalue()
        assert len(list(cache_dir.glob("*.json"))) == 0
