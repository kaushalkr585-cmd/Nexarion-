from __future__ import annotations

import io
from pathlib import Path

import pytest

from code_review.agents.semantic_agent import CrossFileAgent, SemanticAgent
from code_review.cli.main import main, resolve_agents
from code_review.models.enums import AgentType
from code_review.models.finding import Finding
from code_review.orchestrator import ReviewOrchestrator, default_agents
from code_review.parsers.diff_parser import parse_diff

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def cross_file_diff_text() -> str:
    diff_path = FIXTURES_DIR / "sample_cross_file_broken.diff"
    return diff_path.read_text(encoding="utf-8")


@pytest.fixture
def multi_hunk_diff_text() -> str:
    diff_path = FIXTURES_DIR / "sample_multi_hunk_leak.diff"
    return diff_path.read_text(encoding="utf-8")


class TestSemanticAgentContract:
    def test_agent_type_and_name(self) -> None:
        agent = SemanticAgent()
        assert agent.agent_type == AgentType.SEMANTIC
        assert agent.name == "semantic"

    def test_cross_file_agent_alias(self) -> None:
        assert CrossFileAgent is SemanticAgent
        agent = CrossFileAgent()
        assert agent.agent_type == AgentType.SEMANTIC

    def test_empty_diff_returns_empty_findings(self) -> None:
        agent = SemanticAgent()
        assert agent.review([]) == []


class TestSemanticAgentReview:
    def test_review_cross_file_diff(self, cross_file_diff_text: str) -> None:
        diff_files = parse_diff(cross_file_diff_text)
        agent = SemanticAgent()
        findings = agent.review(diff_files)

        assert len(findings) >= 1

        for f in findings:
            assert isinstance(f, Finding)
            assert f.agent == AgentType.SEMANTIC

        rule_ids = {f.rule_id for f in findings}
        assert "SEM002" in rule_ids or "SEM003" in rule_ids or "SEM001" in rule_ids

        for f in findings:
            matching_df = next(df for df in diff_files if df.path == f.file)
            assert f.line in matching_df.added_line_numbers

    def test_review_multi_hunk_diff(self, multi_hunk_diff_text: str) -> None:
        diff_files = parse_diff(multi_hunk_diff_text)
        agent = SemanticAgent()
        findings = agent.review(diff_files)

        assert len(findings) >= 1
        rule_ids = {f.rule_id for f in findings}
        assert "SEM005" in rule_ids

        for f in findings:
            assert f.agent == AgentType.SEMANTIC
            assert f.file == "src/processor.py"


class TestOrchestratorIntegrationWithSemanticAgent:
    def test_default_agents_include_semantic_flag(self) -> None:
        agents_without = default_agents(include_semantic=False)
        assert not any(a.agent_type == AgentType.SEMANTIC for a in agents_without)

        agents_with = default_agents(include_semantic=True)
        assert any(a.agent_type == AgentType.SEMANTIC for a in agents_with)

    def test_orchestrator_initializes_with_semantic(self) -> None:
        orch = ReviewOrchestrator(include_semantic=True)
        assert any(a.agent_type == AgentType.SEMANTIC for a in orch.agents)

    def test_orchestrator_review_diff_with_semantic_agent(self, cross_file_diff_text: str) -> None:
        orch = ReviewOrchestrator(include_semantic=True)
        result = orch.review_diff(cross_file_diff_text)

        assert result.files_reviewed == 2
        assert result.total_findings >= 1

        sem_findings = [f for f in result.findings if f.agent == AgentType.SEMANTIC]
        assert len(sem_findings) >= 1


class TestCLIIntegrationWithSemanticAgent:
    def test_resolve_agents_with_semantic_flag(self) -> None:
        agents = resolve_agents(None, include_llm=False, include_semantic=True)
        types = [a.agent_type for a in agents]
        assert AgentType.SEMANTIC in types

    def test_resolve_agents_by_name(self) -> None:
        agents = resolve_agents("semantic", include_llm=False)
        assert len(agents) == 1
        assert agents[0].agent_type == AgentType.SEMANTIC

    def test_cli_execution_with_semantic_agent(
        self, cross_file_diff_text: str, tmp_path: Path
    ) -> None:
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(cross_file_diff_text, encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = main(
            argv=["--agents", "semantic", str(diff_file), "-f", "json"],
            stdout=stdout,
            stderr=stderr,
        )

        assert exit_code in (0, 1)
        output = stdout.getvalue()
        assert "SEM" in output or "findings" in output
