from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from code_review import __version__
from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.cli.formatter import render_json, render_markdown, render_table
from code_review.cli.git import GitError, get_git_diff, is_git_available, is_git_repo
from code_review.cli.main import (
    build_parser,
    main,
    resolve_agents,
    resolve_diff_input,
)
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult


@pytest.fixture
def sample_finding_info() -> Finding:
    return Finding(
        file="src/utils.py",
        line=10,
        severity=Severity.INFO,
        category=Category.CODE_QUALITY,
        agent=AgentType.AST,
        message="Function has too many branches.",
        suggestion="Split logic into helper functions.",
        rule_id="COMPLEXITY",
    )


@pytest.fixture
def sample_finding_critical() -> Finding:
    return Finding(
        file="src/auth.py",
        line=25,
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        agent=AgentType.BANDIT,
        message="Hardcoded API secret found.",
        suggestion="Use environment variables.",
        rule_id="B105",
    )


@pytest.fixture
def sample_review_result(sample_finding_info, sample_finding_critical) -> ReviewResult:
    return ReviewResult(
        findings=[sample_finding_critical, sample_finding_info],
        files_reviewed=2,
        review_time_ms=125,
    )


@pytest.fixture
def clean_review_result() -> ReviewResult:
    return ReviewResult(
        findings=[],
        files_reviewed=1,
        review_time_ms=12,
    )


class TestArgParser:
    def test_default_arguments(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.target is None
        assert args.staged is False
        assert args.branch is None
        assert args.llm is False
        assert args.agents is None
        assert args.min_severity is None
        assert args.fail_on is None
        assert args.parallel is True
        assert args.format == "table"
        assert args.output_file is None
        assert args.verbose is False

    def test_target_diff_file_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["my_changes.diff"])
        assert args.target == "my_changes.diff"

    def test_stdin_hyphen_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-"])
        assert args.target == "-"

    def test_git_options(self) -> None:
        parser = build_parser()
        args1 = parser.parse_args(["--staged"])
        assert args1.staged is True

        args2 = parser.parse_args(["--cached"])
        assert args2.staged is True

        args3 = parser.parse_args(["--branch", "main"])
        assert args3.branch == "main"

    def test_agent_options(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--llm",
                "--agents",
                "ast,ruff",
                "--min-severity",
                "warning",
                "--fail-on",
                "error",
                "--no-parallel",
            ]
        )
        assert args.llm is True
        assert args.agents == "ast,ruff"
        assert args.min_severity == "warning"
        assert args.fail_on == "error"
        assert args.parallel is False

    def test_output_options(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-f", "json", "-o", "report.json"])
        assert args.format == "json"
        assert args.output_file == Path("report.json")

    def test_version_action(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in captured.out


class TestAgentResolution:
    def test_resolve_default_deterministic_agents(self) -> None:
        agents = resolve_agents(None, include_llm=False)
        agent_types = [a.agent_type for a in agents]
        assert agent_types == [AgentType.AST, AgentType.RUFF, AgentType.BANDIT]

    def test_resolve_default_with_llm(self) -> None:
        agents = resolve_agents(None, include_llm=True)
        agent_types = [a.agent_type for a in agents]
        assert AgentType.LLM in agent_types

    def test_resolve_specific_agents(self) -> None:
        agents = resolve_agents("ast,bandit", include_llm=False)
        assert len(agents) == 2
        assert isinstance(agents[0], ASTAgent)
        assert isinstance(agents[1], BanditAgent)

    def test_resolve_single_agent(self) -> None:
        agents = resolve_agents("ruff", include_llm=False)
        assert len(agents) == 1
        assert isinstance(agents[0], RuffAgent)

    def test_resolve_unknown_agent_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown agent 'unknown_tool'"):
            resolve_agents("ast,unknown_tool", include_llm=False)

    def test_resolve_empty_agents_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="No valid agents specified"):
            resolve_agents("  ,  ", include_llm=False)


class TestGitHelpers:
    def test_is_git_available(self) -> None:
        assert isinstance(is_git_available(), bool)

    def test_is_git_repo(self) -> None:
        assert isinstance(is_git_repo(), bool)

    @patch("shutil.which", return_value=None)
    def test_is_git_available_false_when_no_executable(self, mock_which) -> None:
        assert is_git_available() is False

    @patch("subprocess.run")
    def test_get_git_diff_working_tree(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff"], returncode=0, stdout="diff --git a/test.py"
        )
        with patch("code_review.cli.git.is_git_repo", return_value=True):
            diff = get_git_diff(staged=False)
            assert diff == "diff --git a/test.py"

    @patch("subprocess.run")
    def test_get_git_diff_staged(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "--cached"], returncode=0, stdout="staged diff"
        )
        with patch("code_review.cli.git.is_git_repo", return_value=True):
            diff = get_git_diff(staged=True)
            assert diff == "staged diff"

    @patch("subprocess.run")
    def test_get_git_diff_branch(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "main...HEAD"], returncode=0, stdout="branch diff"
        )
        with patch("code_review.cli.git.is_git_repo", return_value=True):
            diff = get_git_diff(branch="main")
            assert diff == "branch diff"

    @patch("code_review.cli.git.is_git_available", return_value=False)
    def test_get_git_diff_raises_when_git_unavailable(self, mock_git_avail) -> None:
        with pytest.raises(GitError, match="Git executable not found"):
            get_git_diff()

    @patch("code_review.cli.git.is_git_available", return_value=True)
    @patch("code_review.cli.git.is_git_repo", return_value=False)
    def test_get_git_diff_raises_when_not_in_repo(self, mock_repo, mock_avail) -> None:
        with pytest.raises(GitError, match="not inside a git repository"):
            get_git_diff()

    @patch("code_review.cli.git.is_git_available", return_value=True)
    @patch("code_review.cli.git.is_git_repo", return_value=True)
    @patch("subprocess.run")
    def test_get_git_diff_raises_on_command_failure(self, mock_run, mock_repo, mock_avail) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff"], returncode=128, stdout="", stderr="fatal error"
        )
        with pytest.raises(GitError, match="Git diff failed"):
            get_git_diff()


class TestDiffResolution:
    def test_resolve_from_valid_file(self) -> None:
        fixture_path = "tests/fixtures/sample.diff"
        diff = resolve_diff_input(fixture_path)
        assert "check_password" in diff

    def test_resolve_from_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Diff file not found"):
            resolve_diff_input("nonexistent_path_123.diff")

    def test_resolve_from_stdin_hyphen(self) -> None:
        fake_stdin = io.StringIO("diff --git a/foo.py b/foo.py\n+added")
        fake_stdin.isatty = lambda: True  # type: ignore[assignment]
        diff = resolve_diff_input("-", stdin=fake_stdin)
        assert "+added" in diff

    def test_resolve_from_piped_stdin(self) -> None:
        fake_stdin = io.StringIO("diff --git a/piped.py b/piped.py\n+piped line")
        fake_stdin.isatty = lambda: False  # type: ignore[assignment]
        diff = resolve_diff_input(None, stdin=fake_stdin)
        assert "+piped line" in diff

    @patch("code_review.cli.main.is_git_repo", return_value=False)
    def test_resolve_no_diff_and_not_in_git_repo_raises_value_error(self, mock_git) -> None:
        fake_stdin = io.StringIO("")
        fake_stdin.isatty = lambda: True  # type: ignore[assignment]
        with pytest.raises(ValueError, match="No diff input provided"):
            resolve_diff_input(None, stdin=fake_stdin)


class TestFormatters:
    def test_render_table_with_findings(self, sample_review_result) -> None:
        out = io.StringIO()
        console = Console(file=out, force_terminal=False, width=120)
        render_table(sample_review_result, console=console)
        output = out.getvalue()

        assert "Multi-Agent Code Review Results" in output
        assert "Total Findings: 2" in output
        assert "CRITICAL" in output
        assert "INFO" in output
        assert "src/auth.py" in output
        assert "src/utils.py" in output
        assert "Hardcoded API secret found." in output

    def test_render_table_clean_results(self, clean_review_result) -> None:
        out = io.StringIO()
        console = Console(file=out, force_terminal=False, width=120)
        render_table(clean_review_result, console=console)
        output = out.getvalue()

        assert "Multi-Agent Code Review Results" in output
        assert "Total Findings: 0" in output
        assert "No issues detected" in output

    def test_render_json(self, sample_review_result) -> None:
        json_str = render_json(sample_review_result)
        data = json.loads(json_str)

        assert data["files_reviewed"] == 2
        assert data["total_findings"] == 2
        assert len(data["findings"]) == 2
        assert data["findings"][0]["severity"] == "critical"
        assert data["findings"][1]["severity"] == "info"

    def test_render_markdown_with_findings(self, sample_review_result) -> None:
        md = render_markdown(sample_review_result)

        assert "# Multi-Agent Code Review Report" in md
        assert "**Files Reviewed:** 2" in md
        assert "| Critical | Error | Warning | Info |" in md
        assert "| 1 | 0 | 0 | 1 |" in md
        assert "`src/auth.py:25`" in md
        assert "Hardcoded API secret found." in md
        assert "Use environment variables." in md

    def test_render_markdown_clean_results(self, clean_review_result) -> None:
        md = render_markdown(clean_review_result)

        assert "# Multi-Agent Code Review Report" in md
        assert "**Files Reviewed:** 1" in md
        assert "No issues detected" in md


class TestMainExecution:
    def test_main_with_sample_diff(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["tests/fixtures/sample.diff"],
            stdout=stdout,
            stderr=stderr,
        )
        assert code == 0
        assert "Multi-Agent Code Review Results" in stdout.getvalue()

    def test_main_with_format_json(self) -> None:
        stdout = io.StringIO()
        code = main(
            ["tests/fixtures/sample_issues.diff", "--format", "json"],
            stdout=stdout,
        )
        assert code == 0
        data = json.loads(stdout.getvalue())
        assert "findings" in data
        assert data["files_reviewed"] == 1

    def test_main_with_format_markdown(self) -> None:
        stdout = io.StringIO()
        code = main(
            ["tests/fixtures/sample_issues.diff", "--format", "markdown"],
            stdout=stdout,
        )
        assert code == 0
        out = stdout.getvalue()
        assert "# Multi-Agent Code Review Report" in out

    def test_main_with_output_file(self, tmp_path: Path) -> None:
        out_file = tmp_path / "review_report.json"
        stdout = io.StringIO()
        code = main(
            [
                "tests/fixtures/sample_issues.diff",
                "--format",
                "json",
                "-o",
                str(out_file),
            ],
            stdout=stdout,
        )
        assert code == 0
        assert out_file.exists()
        saved = json.loads(out_file.read_text(encoding="utf-8"))
        assert saved["total_findings"] == 1

    def test_main_with_nonexistent_file_returns_code_2(self) -> None:
        stderr = io.StringIO()
        code = main(["nonexistent.diff"], stderr=stderr)
        assert code == 2
        assert "Input error" in stderr.getvalue()

    def test_main_with_invalid_agent_returns_code_2(self) -> None:
        stderr = io.StringIO()
        code = main(
            ["tests/fixtures/sample.diff", "--agents", "fake_agent"],
            stderr=stderr,
        )
        assert code == 2
        assert "Configuration error" in stderr.getvalue()

    def test_main_empty_diff_returns_code_0(self, tmp_path: Path) -> None:
        empty_diff = tmp_path / "empty.diff"
        empty_diff.write_text("", encoding="utf-8")

        stdout = io.StringIO()
        code = main([str(empty_diff)], stdout=stdout)
        assert code == 0
        assert "No diff changes detected" in stdout.getvalue()


class TestQualityGateExitCodes:
    def test_fail_on_critical_passes_when_only_info(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["tests/fixtures/sample_issues.diff", "--fail-on", "critical"],
            stdout=stdout,
            stderr=stderr,
        )
        assert code == 0
        assert "Quality Gate Failed" not in stderr.getvalue()

    def test_fail_on_info_fails_when_info_finding_present(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["tests/fixtures/sample_issues.diff", "--fail-on", "info"],
            stdout=stdout,
            stderr=stderr,
        )
        assert code == 1
        assert "Quality Gate Failed" in stderr.getvalue()

    def test_fail_on_clean_diff_passes(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(
            ["tests/fixtures/sample.diff", "--fail-on", "error"],
            stdout=stdout,
            stderr=stderr,
        )
        assert code == 0

    def test_no_fail_on_returns_0_even_with_findings(self) -> None:
        stdout = io.StringIO()
        code = main(
            ["tests/fixtures/sample_issues.diff"],
            stdout=stdout,
        )
        assert code == 0


class TestCLIWithMockedAgent:
    def test_min_severity_filters_lower_severities(self) -> None:
        stdout = io.StringIO()

        code = main(
            [
                "tests/fixtures/sample_issues.diff",
                "--min-severity",
                "warning",
                "--format",
                "json",
            ],
            stdout=stdout,
        )
        assert code == 0
        data = json.loads(stdout.getvalue())
        assert data["total_findings"] == 0

    def test_main_with_stdin_pipe(self) -> None:
        diff_content = Path("tests/fixtures/sample_issues.diff").read_text(encoding="utf-8")
        stdin = io.StringIO(diff_content)
        stdin.isatty = lambda: False  # type: ignore[assignment]
        stdout = io.StringIO()

        code = main(["-", "--format", "json"], stdin=stdin, stdout=stdout)
        assert code == 0
        data = json.loads(stdout.getvalue())
        assert data["total_findings"] == 1
