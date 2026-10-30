import json
from pathlib import Path
from unittest.mock import patch

from code_review.agents.ruff_agent import RuffAgent, _map_ruff_category, _map_ruff_severity
from code_review.models.enums import AgentType, Category, Severity
from code_review.parsers.diff_parser import DiffFile, DiffHunk, DiffLine, LineType


class TestRuffAgentInit:
    def test_agent_type_is_ruff(self) -> None:
        agent = RuffAgent()
        assert agent.agent_type == AgentType.RUFF

    def test_name_is_ruff(self) -> None:
        agent = RuffAgent()
        assert agent.name == "ruff"

    def test_default_cmd(self) -> None:
        agent = RuffAgent()
        assert "ruff" in agent.ruff_cmd[-1]

    def test_custom_cmd_and_timeout(self) -> None:
        agent = RuffAgent(ruff_cmd=["custom-ruff"], timeout=15)
        assert agent.ruff_cmd == ["custom-ruff"]
        assert agent.timeout == 15


class TestRuffMappings:
    def test_category_mapping(self) -> None:
        assert _map_ruff_category("S101") == Category.SECURITY
        assert _map_ruff_category("F401") == Category.BUG_RISK
        assert _map_ruff_category("F821") == Category.BUG_RISK
        assert _map_ruff_category("B006") == Category.BUG_RISK
        assert _map_ruff_category("PERF101") == Category.PERFORMANCE
        assert _map_ruff_category("D100") == Category.DOCUMENTATION
        assert _map_ruff_category("E501") == Category.CODE_QUALITY
        assert _map_ruff_category("I001") == Category.CODE_QUALITY
        assert _map_ruff_category("UP006") == Category.CODE_QUALITY
        assert _map_ruff_category("UNKNOWN") == Category.CODE_QUALITY

    def test_severity_mapping(self) -> None:
        assert _map_ruff_severity("E999") == Severity.ERROR
        assert _map_ruff_severity("F821") == Severity.ERROR
        assert _map_ruff_severity("S101") == Severity.ERROR
        assert _map_ruff_severity("I001") == Severity.INFO
        assert _map_ruff_severity("D100") == Severity.INFO
        assert _map_ruff_severity("F401") == Severity.WARNING
        assert _map_ruff_severity("E501") == Severity.WARNING


class TestRuffOutputParsing:
    def test_empty_output_returns_empty_list(self) -> None:
        agent = RuffAgent()
        assert agent.parse_ruff_output("") == []
        assert agent.parse_ruff_output("   ") == []

    def test_invalid_json_returns_empty_list(self) -> None:
        agent = RuffAgent()
        assert agent.parse_ruff_output("Not valid json") == []

    def test_valid_json_parsed(self) -> None:
        agent = RuffAgent()
        sample_json = json.dumps(
            [
                {
                    "code": "F401",
                    "message": "`os` imported but unused",
                    "location": {"row": 5, "column": 1},
                    "filename": "src/utils.py",
                    "fix": {"message": "Remove unused import: `os`"},
                }
            ]
        )
        findings = agent.parse_ruff_output(sample_json)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.file == "src/utils.py"
        assert finding.line == 5
        assert finding.rule_id == "F401"
        assert finding.message == "`os` imported but unused"
        assert finding.suggestion == "Remove unused import: `os`"
        assert finding.agent == AgentType.RUFF
        assert finding.category == Category.BUG_RISK
        assert finding.severity == Severity.WARNING

    def test_diff_filtering_in_parsing(self) -> None:
        agent = RuffAgent()
        sample_json = json.dumps(
            [
                {
                    "code": "F401",
                    "message": "`os` imported but unused",
                    "location": {"row": 5, "column": 1},
                    "filename": "src/utils.py",
                },
                {
                    "code": "F841",
                    "message": "Local variable `x` unused",
                    "location": {"row": 12, "column": 1},
                    "filename": "src/utils.py",
                },
            ]
        )

        findings = agent.parse_ruff_output(sample_json, added_lines=frozenset({12}))
        assert len(findings) == 1
        assert findings[0].line == 12
        assert findings[0].rule_id == "F841"


class TestRuffReview:
    def test_review_sample_lint_issues_fixture(self) -> None:
        repo_root = Path(__file__).parent.parent
        agent = RuffAgent(repo_root=repo_root)
        fixture_path = "tests/fixtures/sample_lint_issues.py"

        diff_file = DiffFile(
            source_file=f"a/{fixture_path}",
            target_file=f"b/{fixture_path}",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=20,
                    target_start=1,
                    target_length=20,
                    lines=(
                        DiffLine(line_type=LineType.ADDED, content="import sys", target_line=6),
                        DiffLine(line_type=LineType.ADDED, content="import os", target_line=7),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="unused_var = ...",
                            target_line=12,
                        ),
                    ),
                ),
            ),
        )

        findings = agent.review([diff_file])
        assert len(findings) >= 2
        for f in findings:
            assert f.file == fixture_path
            assert f.line in {6, 7, 12}
            assert f.agent == AgentType.RUFF

    def test_review_skips_non_python_files(self) -> None:
        agent = RuffAgent()
        diff_file = DiffFile(
            source_file="a/README.md",
            target_file="b/README.md",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=1,
                    target_start=1,
                    target_length=1,
                    lines=(DiffLine(line_type=LineType.ADDED, content="# Readme", target_line=1),),
                ),
            ),
        )
        findings = agent.review([diff_file])
        assert findings == []

    def test_review_skips_nonexistent_file(self) -> None:
        agent = RuffAgent()
        diff_file = DiffFile(
            source_file="a/missing.py",
            target_file="b/missing.py",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=1,
                    target_start=1,
                    target_length=1,
                    lines=(DiffLine(line_type=LineType.ADDED, content="a = 1", target_line=1),),
                ),
            ),
        )
        findings = agent.review([diff_file])
        assert findings == []

    @patch("subprocess.run")
    def test_timeout_handled_gracefully(self, mock_run) -> None:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ruff"], timeout=10)
        agent = RuffAgent()
        findings = agent.run_ruff(__file__)
        assert findings == []

    @patch("subprocess.run")
    def test_file_not_found_handled_gracefully(self, mock_run) -> None:
        mock_run.side_effect = FileNotFoundError("Executable not found")
        agent = RuffAgent()
        findings = agent.run_ruff(__file__)
        assert findings == []
