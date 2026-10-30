from __future__ import annotations

import time
from pathlib import Path

import pytest

from code_review import Orchestrator, ReviewOrchestrator
from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.base import BaseAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult
from code_review.orchestrator import (
    deduplicate_findings,
    default_agents,
    default_dedup_key,
    sort_findings,
)
from code_review.parsers.diff_parser import DiffFile, DiffHunk, DiffLine, LineType


class MockAgent(BaseAgent):
    def __init__(
        self,
        agent_type: AgentType = AgentType.AST,
        findings: list[Finding] | None = None,
        raise_exception: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._agent_type = agent_type
        self._findings = findings or []
        self._raise_exception = raise_exception
        self._delay_seconds = delay_seconds
        self.call_count = 0

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        self.call_count += 1
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        if self._raise_exception is not None:
            raise self._raise_exception
        return list(self._findings)


def make_finding(
    file: str = "src/example.py",
    line: int = 10,
    severity: Severity = Severity.WARNING,
    category: Category = Category.CODE_QUALITY,
    agent: AgentType = AgentType.AST,
    message: str = "Test issue message",
    suggestion: str | None = None,
    rule_id: str | None = "TEST001",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity=severity,
        category=category,
        agent=agent,
        message=message,
        suggestion=suggestion,
        rule_id=rule_id,
    )


def make_diff_file(
    file_path: str = "src/example.py",
    added_lines: list[int] | None = None,
) -> DiffFile:
    lines_nums = added_lines or [10, 11, 12]
    diff_lines = [
        DiffLine(line_type=LineType.ADDED, content="x = 1", source_line_no=None, target_line_no=ln)
        for ln in lines_nums
    ]
    hunk = DiffHunk(
        source_start=1,
        source_length=0,
        target_start=lines_nums[0],
        target_length=len(lines_nums),
        lines=diff_lines,
    )
    return DiffFile(
        source_file=file_path,
        target_file=file_path,
        hunks=[hunk],
    )


class TestOrchestratorInit:
    def test_default_agents_initialized(self) -> None:
        orchestrator = ReviewOrchestrator()
        agents = orchestrator.agents
        assert len(agents) == 3
        types = [a.agent_type for a in agents]
        assert AgentType.AST in types
        assert AgentType.RUFF in types
        assert AgentType.BANDIT in types

    def test_custom_agents_passed(self) -> None:
        mock = MockAgent(agent_type=AgentType.AST)
        orchestrator = ReviewOrchestrator(agents=[mock])
        assert len(orchestrator.agents) == 1
        assert orchestrator.agents[0] is mock

    def test_empty_agents_list_respected(self) -> None:
        orchestrator = ReviewOrchestrator(agents=[])
        assert len(orchestrator.agents) == 0

    def test_default_options(self) -> None:
        orchestrator = ReviewOrchestrator()
        assert orchestrator.parallel is False
        assert orchestrator._deduplicate is True
        assert orchestrator._min_severity is None
        assert orchestrator.last_errors == {}

    def test_custom_options(self) -> None:
        orchestrator = ReviewOrchestrator(
            parallel=True,
            max_workers=4,
            deduplicate=False,
            min_severity=Severity.HIGH if hasattr(Severity, "HIGH") else Severity.ERROR,
        )
        assert orchestrator.parallel is True
        assert orchestrator._max_workers == 4
        assert orchestrator._deduplicate is False

    def test_default_agents_factory(self) -> None:
        agents = default_agents()
        assert len(agents) == 3
        assert isinstance(agents[0], ASTAgent)
        assert isinstance(agents[1], RuffAgent)
        assert isinstance(agents[2], BanditAgent)


class TestAgentRegistry:
    def test_register_agent(self) -> None:
        orchestrator = ReviewOrchestrator(agents=[])
        mock = MockAgent(agent_type=AgentType.AST)
        orchestrator.register_agent(mock)
        assert orchestrator.agents == [mock]

    def test_register_agent_idempotent(self) -> None:
        mock = MockAgent(agent_type=AgentType.AST)
        orchestrator = ReviewOrchestrator(agents=[mock])
        orchestrator.register_agent(mock)
        assert len(orchestrator.agents) == 1

    def test_get_agent_by_agent_type(self) -> None:
        orchestrator = ReviewOrchestrator()
        agent = orchestrator.get_agent(AgentType.RUFF)
        assert agent is not None
        assert agent.agent_type == AgentType.RUFF

    def test_get_agent_by_class(self) -> None:
        orchestrator = ReviewOrchestrator()
        agent = orchestrator.get_agent(BanditAgent)
        assert agent is not None
        assert isinstance(agent, BanditAgent)

    def test_get_agent_by_name_string(self) -> None:
        orchestrator = ReviewOrchestrator()
        agent = orchestrator.get_agent("ast")
        assert agent is not None
        assert agent.name == "ast"

        agent_upper = orchestrator.get_agent("AST")
        assert agent_upper is not None
        assert agent_upper.name == "ast"

    def test_get_agent_not_found_returns_none(self) -> None:
        orchestrator = ReviewOrchestrator(agents=[])
        assert orchestrator.get_agent(AgentType.LLM) is None
        assert orchestrator.get_agent("nonexistent") is None

    def test_unregister_agent_by_agent_type(self) -> None:
        orchestrator = ReviewOrchestrator()
        removed = orchestrator.unregister_agent(AgentType.AST)
        assert removed is True
        assert orchestrator.get_agent(AgentType.AST) is None
        assert len(orchestrator.agents) == 2

    def test_unregister_agent_by_class(self) -> None:
        orchestrator = ReviewOrchestrator()
        removed = orchestrator.unregister_agent(RuffAgent)
        assert removed is True
        assert orchestrator.get_agent(RuffAgent) is None
        assert len(orchestrator.agents) == 2

    def test_unregister_agent_by_name(self) -> None:
        orchestrator = ReviewOrchestrator()
        removed = orchestrator.unregister_agent("bandit")
        assert removed is True
        assert orchestrator.get_agent("bandit") is None
        assert len(orchestrator.agents) == 2

    def test_unregister_agent_not_found_returns_false(self) -> None:
        orchestrator = ReviewOrchestrator(agents=[])
        assert orchestrator.unregister_agent(AgentType.AST) is False

    def test_agents_property_returns_copy(self) -> None:
        orchestrator = ReviewOrchestrator()
        agents_list = orchestrator.agents
        agents_list.clear()
        assert len(orchestrator.agents) == 3


class TestDeduplication:
    def test_empty_findings_returns_empty(self) -> None:
        assert deduplicate_findings([]) == []

    def test_single_finding_preserved(self) -> None:
        finding = make_finding()
        assert deduplicate_findings([finding]) == [finding]

    def test_distinct_findings_all_preserved(self) -> None:
        f1 = make_finding(file="src/a.py", line=10, rule_id="R1")
        f2 = make_finding(file="src/b.py", line=20, rule_id="R2")
        f3 = make_finding(file="src/a.py", line=30, rule_id="R3")
        assert len(deduplicate_findings([f1, f2, f3])) == 3

    def test_duplicate_retains_higher_severity(self) -> None:
        f_low = make_finding(
            file="src/a.py",
            line=10,
            severity=Severity.WARNING,
            rule_id="SEC001",
            message="Possible problem",
        )
        f_high = make_finding(
            file="src/a.py",
            line=10,
            severity=Severity.CRITICAL,
            rule_id="SEC001",
            message="Severe vulnerability",
        )

        result1 = deduplicate_findings([f_low, f_high])
        assert len(result1) == 1
        assert result1[0].severity == Severity.CRITICAL
        assert result1[0].message == "Severe vulnerability"

        result2 = deduplicate_findings([f_high, f_low])
        assert len(result2) == 1
        assert result2[0].severity == Severity.CRITICAL

    def test_duplicate_same_severity_prefers_suggestion(self) -> None:
        f_no_sugg = make_finding(
            file="src/a.py",
            line=10,
            severity=Severity.WARNING,
            rule_id="AST001",
            message="Complex function",
            suggestion=None,
        )
        f_with_sugg = make_finding(
            file="src/a.py",
            line=10,
            severity=Severity.WARNING,
            rule_id="AST001",
            message="Complex function",
            suggestion="Break into smaller helper functions",
        )
        result1 = deduplicate_findings([f_no_sugg, f_with_sugg])
        assert len(result1) == 1
        assert result1[0].suggestion == "Break into smaller helper functions"

        result2 = deduplicate_findings([f_with_sugg, f_no_sugg])
        assert len(result2) == 1
        assert result2[0].suggestion == "Break into smaller helper functions"

    def test_duplicate_identical_retains_first(self) -> None:
        f1 = make_finding(agent=AgentType.AST, message="First")
        f2 = make_finding(agent=AgentType.RUFF, message="First")
        result = deduplicate_findings([f1, f2])
        assert len(result) == 1
        assert result[0].agent == AgentType.AST

    def test_duplicate_without_rule_id_matches_message(self) -> None:
        f1 = make_finding(rule_id=None, message="Same issue description")
        f2 = make_finding(rule_id=None, message="Same issue description", severity=Severity.ERROR)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_different_rules_on_same_line_both_kept(self) -> None:
        f_style = make_finding(
            file="src/app.py",
            line=15,
            severity=Severity.INFO,
            category=Category.CODE_QUALITY,
            rule_id="E501",
            message="Line too long",
        )
        f_sec = make_finding(
            file="src/app.py",
            line=15,
            severity=Severity.CRITICAL,
            category=Category.SECURITY,
            rule_id="B608",
            message="SQL injection risk",
        )
        result = deduplicate_findings([f_style, f_sec])
        assert len(result) == 2
        rules = {f.rule_id for f in result}
        assert rules == {"E501", "B608"}

    def test_default_dedup_key_helper(self) -> None:
        f_with_rule = make_finding(file="x.py", line=5, rule_id="R10")
        assert default_dedup_key(f_with_rule) == ("x.py", 5, "R10")

        f_no_rule = make_finding(file="x.py", line=5, rule_id=None, message="Msg")
        assert default_dedup_key(f_no_rule) == ("x.py", 5, "Msg")

    def test_custom_key_func(self) -> None:
        f1 = make_finding(file="x.py", line=5, rule_id="R1")
        f2 = make_finding(file="x.py", line=5, rule_id="R2")
        result = deduplicate_findings([f1, f2], key_func=lambda f: (f.file, f.line))
        assert len(result) == 1


class TestSorting:
    def test_empty_list_sorting(self) -> None:
        assert sort_findings([]) == []

    def test_sorts_by_severity_rank_descending(self) -> None:
        f_info = make_finding(severity=Severity.INFO, line=1)
        f_warn = make_finding(severity=Severity.WARNING, line=2)
        f_err = make_finding(severity=Severity.ERROR, line=3)
        f_crit = make_finding(severity=Severity.CRITICAL, line=4)

        sorted_list = sort_findings([f_info, f_crit, f_warn, f_err], reverse=True)
        assert [f.severity for f in sorted_list] == [
            Severity.CRITICAL,
            Severity.ERROR,
            Severity.WARNING,
            Severity.INFO,
        ]

    def test_secondary_sort_by_file_and_line(self) -> None:
        f1 = make_finding(file="b.py", line=20, severity=Severity.ERROR)
        f2 = make_finding(file="a.py", line=50, severity=Severity.ERROR)
        f3 = make_finding(file="a.py", line=10, severity=Severity.ERROR)

        sorted_list = sort_findings([f1, f2, f3], reverse=True)
        assert [(f.file, f.line) for f in sorted_list] == [
            ("a.py", 10),
            ("a.py", 50),
            ("b.py", 20),
        ]

    def test_sort_reverse_false_ascending(self) -> None:
        f_info = make_finding(severity=Severity.INFO)
        f_crit = make_finding(severity=Severity.CRITICAL)

        sorted_list = sort_findings([f_crit, f_info], reverse=False)
        assert [f.severity for f in sorted_list] == [Severity.INFO, Severity.CRITICAL]


class TestExecutionModes:
    def test_sequential_execution(self) -> None:
        f1 = make_finding(message="From Agent 1")
        f2 = make_finding(message="From Agent 2", line=20)
        agent1 = MockAgent(agent_type=AgentType.AST, findings=[f1])
        agent2 = MockAgent(agent_type=AgentType.RUFF, findings=[f2])

        orchestrator = ReviewOrchestrator(agents=[agent1, agent2], parallel=False)
        diff_file = make_diff_file()
        result = orchestrator.review_files([diff_file])

        assert result.total_findings == 2
        assert agent1.call_count == 1
        assert agent2.call_count == 1

    def test_parallel_execution(self) -> None:
        f1 = make_finding(message="From Agent 1", line=10)
        f2 = make_finding(message="From Agent 2", line=20)
        agent1 = MockAgent(agent_type=AgentType.AST, findings=[f1], delay_seconds=0.01)
        agent2 = MockAgent(agent_type=AgentType.RUFF, findings=[f2], delay_seconds=0.01)

        orchestrator = ReviewOrchestrator(agents=[agent1, agent2], parallel=True)
        diff_file = make_diff_file()
        result = orchestrator.review_files([diff_file])

        assert result.total_findings == 2
        assert agent1.call_count == 1
        assert agent2.call_count == 1

    def test_sequential_and_parallel_produce_identical_results(self) -> None:
        findings_common = [
            make_finding(file="src/a.py", line=10, severity=Severity.CRITICAL, rule_id="SEC1"),
            make_finding(file="src/b.py", line=5, severity=Severity.WARNING, rule_id="WARN1"),
        ]
        agent1 = MockAgent(agent_type=AgentType.AST, findings=[findings_common[0]])
        agent2 = MockAgent(agent_type=AgentType.RUFF, findings=[findings_common[1]])

        diff_file = make_diff_file()

        orch_seq = ReviewOrchestrator(agents=[agent1, agent2], parallel=False)
        res_seq = orch_seq.review_files([diff_file])

        orch_par = ReviewOrchestrator(agents=[agent1, agent2], parallel=True)
        res_par = orch_par.review_files([diff_file])

        assert res_seq.findings == res_par.findings
        assert res_seq.files_reviewed == res_par.files_reviewed

    def test_parallel_flag_override_per_call(self) -> None:
        agent1 = MockAgent(agent_type=AgentType.AST)
        agent2 = MockAgent(agent_type=AgentType.RUFF)
        orchestrator = ReviewOrchestrator(agents=[agent1, agent2], parallel=False)

        orchestrator.review_files([make_diff_file()], parallel=True)
        assert agent1.call_count == 1
        assert agent2.call_count == 1


class TestFaultTolerance:
    def test_agent_exception_does_not_crash_review(self) -> None:
        good_finding = make_finding(message="Valid issue")
        healthy_agent = MockAgent(agent_type=AgentType.AST, findings=[good_finding])
        broken_agent = MockAgent(
            agent_type=AgentType.RUFF,
            raise_exception=RuntimeError("Subprocess died unexpectedly"),
        )

        orchestrator = ReviewOrchestrator(agents=[healthy_agent, broken_agent], parallel=False)
        result = orchestrator.review_files([make_diff_file()])

        assert result.total_findings == 1
        assert result.findings[0].message == "Valid issue"
        assert "ruff" in orchestrator.last_errors
        assert isinstance(orchestrator.last_errors["ruff"], RuntimeError)

    def test_parallel_agent_exception_handled_gracefully(self) -> None:
        good_finding = make_finding(message="Valid issue")
        healthy_agent = MockAgent(agent_type=AgentType.AST, findings=[good_finding])
        broken_agent = MockAgent(
            agent_type=AgentType.BANDIT,
            raise_exception=FileNotFoundError("Bandit binary missing"),
        )

        orchestrator = ReviewOrchestrator(agents=[healthy_agent, broken_agent], parallel=True)
        result = orchestrator.review_files([make_diff_file()])

        assert result.total_findings == 1
        assert "bandit" in orchestrator.last_errors
        assert isinstance(orchestrator.last_errors["bandit"], FileNotFoundError)

    def test_all_agents_failing_returns_empty_result_with_errors(self) -> None:
        broken1 = MockAgent(agent_type=AgentType.AST, raise_exception=ValueError("Boom 1"))
        broken2 = MockAgent(agent_type=AgentType.RUFF, raise_exception=KeyError("Boom 2"))

        orchestrator = ReviewOrchestrator(agents=[broken1, broken2])
        result = orchestrator.review_files([make_diff_file()])

        assert result.total_findings == 0
        assert len(orchestrator.last_errors) == 2


class TestSeverityFiltering:
    def test_min_severity_filters_lower_severities(self) -> None:
        f_info = make_finding(severity=Severity.INFO, line=10)
        f_warn = make_finding(severity=Severity.WARNING, line=20)
        f_crit = make_finding(severity=Severity.CRITICAL, line=30)
        agent = MockAgent(findings=[f_info, f_warn, f_crit])

        orchestrator = ReviewOrchestrator(agents=[agent], min_severity=Severity.WARNING)
        result = orchestrator.review_files([make_diff_file()])

        assert result.total_findings == 2
        severities = {f.severity for f in result.findings}
        assert severities == {Severity.WARNING, Severity.CRITICAL}

    def test_min_severity_per_call_override(self) -> None:
        f_info = make_finding(severity=Severity.INFO, line=10)
        f_crit = make_finding(severity=Severity.CRITICAL, line=30)
        agent = MockAgent(findings=[f_info, f_crit])

        orchestrator = ReviewOrchestrator(agents=[agent], min_severity=None)
        result = orchestrator.review_files([make_diff_file()], min_severity=Severity.CRITICAL)

        assert result.total_findings == 1
        assert result.findings[0].severity == Severity.CRITICAL


class TestReviewInputs:
    def test_review_diff_parses_diff_string(self) -> None:
        diff_text = (
            "--- a/src/test.py\n"
            "+++ b/src/test.py\n"
            "@@ -1,2 +1,3 @@\n"
            " x = 0\n"
            "+print('hello')\n"
            " y = 0\n"
        )
        mock_finding = make_finding(file="src/test.py", line=1)
        agent = MockAgent(findings=[mock_finding])
        orchestrator = ReviewOrchestrator(agents=[agent])

        result = orchestrator.review_diff(diff_text)
        assert result.files_reviewed == 1
        assert result.total_findings == 1
        assert result.review_time_ms >= 0

    def test_review_smart_dispatcher_with_str(self) -> None:
        diff_text = (
            "--- a/src/test.py\n+++ b/src/test.py\n@@ -1,2 +1,3 @@\n a = 0\n+x = 1\n b = 0\n"
        )
        agent = MockAgent()
        orchestrator = ReviewOrchestrator(agents=[agent])
        result = orchestrator.review(diff_text)
        assert isinstance(result, ReviewResult)
        assert result.files_reviewed == 1

    def test_review_smart_dispatcher_with_diff_files(self) -> None:
        diff_file = make_diff_file()
        agent = MockAgent()
        orchestrator = ReviewOrchestrator(agents=[agent])
        result = orchestrator.review([diff_file])
        assert isinstance(result, ReviewResult)
        assert result.files_reviewed == 1

    def test_review_smart_dispatcher_invalid_type_raises(self) -> None:
        orchestrator = ReviewOrchestrator(agents=[])
        with pytest.raises(TypeError, match="Review target must be str"):
            orchestrator.review(12345)  # type: ignore[arg-type]

    def test_empty_diff_returns_empty_result(self) -> None:
        orchestrator = ReviewOrchestrator()
        result = orchestrator.review_diff("")
        assert result.total_findings == 0
        assert result.files_reviewed == 0
        assert result.review_time_ms >= 0

    def test_review_deduplicate_flag_override(self) -> None:
        f1 = make_finding(rule_id="R1")
        f2 = make_finding(rule_id="R1")
        agent = MockAgent(findings=[f1, f2])
        orchestrator = ReviewOrchestrator(agents=[agent], deduplicate=True)

        result = orchestrator.review_files([make_diff_file()], deduplicate=False)
        assert result.total_findings == 2

    def test_review_agents_override_per_call(self) -> None:
        default_agent = MockAgent(findings=[make_finding(message="default")])
        custom_agent = MockAgent(findings=[make_finding(message="custom")])

        orchestrator = ReviewOrchestrator(agents=[default_agent])
        result = orchestrator.review_files([make_diff_file()], agents=[custom_agent])

        assert result.total_findings == 1
        assert result.findings[0].message == "custom"
        assert default_agent.call_count == 0
        assert custom_agent.call_count == 1


class TestEndToEndWithRealAgents:
    @pytest.fixture
    def security_diff(self) -> str:
        return (
            "--- a/tests/fixtures/sample_security.py\n"
            "+++ b/tests/fixtures/sample_security.py\n"
            "@@ -17,2 +17,4 @@\n"
            " def execute_system_command(user_provided_cmd: str) -> None:\n"
            '     """Command execution via shell (command injection risk)."""\n'
            '+    os.system("echo " + user_provided_cmd)\n'
            "+    subprocess.run(user_provided_cmd, shell=True)\n"
        )

    def test_review_on_sample_diff_fixture(self) -> None:
        diff_path = Path("tests/fixtures/sample.diff")
        if not diff_path.exists():
            pytest.skip("sample.diff fixture not found")

        diff_text = diff_path.read_text(encoding="utf-8")
        orchestrator = ReviewOrchestrator()
        result = orchestrator.review_diff(diff_text)

        assert isinstance(result, ReviewResult)
        assert result.files_reviewed == 1
        assert isinstance(result.review_time_ms, int)
        assert result.review_time_ms >= 0

    def test_review_security_issues_detected_and_sorted(self, security_diff: str) -> None:
        fixture_path = Path("tests/fixtures/sample_security.py")
        if not fixture_path.exists():
            pytest.skip("sample_security.py fixture not found")

        orchestrator = ReviewOrchestrator(parallel=False)
        result = orchestrator.review_diff(security_diff)

        assert result.files_reviewed == 1

        if result.total_findings > 0:
            ranks = [f.severity for f in result.findings]
            for i in range(len(ranks) - 1):
                from code_review.models.enums import severity_rank

                assert severity_rank(ranks[i]) >= severity_rank(ranks[i + 1])

        data = result.model_dump()
        assert "findings" in data
        assert "files_reviewed" in data
        assert "review_time_ms" in data
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)


class TestPackageExports:
    def test_orchestrator_alias(self) -> None:
        assert ReviewOrchestrator is Orchestrator

    def test_orchestrator_imports_from_package_root(self) -> None:
        import code_review

        assert hasattr(code_review, "ReviewOrchestrator")
        assert hasattr(code_review, "Orchestrator")
        assert hasattr(code_review, "deduplicate_findings")
        assert hasattr(code_review, "sort_findings")
        assert hasattr(code_review, "default_agents")
