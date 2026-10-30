import json
from pathlib import Path
from unittest.mock import patch

from code_review.agents.bandit_agent import BanditAgent, _map_bandit_severity
from code_review.models.enums import AgentType, Category, Severity
from code_review.parsers.diff_parser import DiffFile, DiffHunk, DiffLine, LineType


class TestBanditAgentInit:
    def test_agent_type_is_bandit(self) -> None:
        agent = BanditAgent()
        assert agent.agent_type == AgentType.BANDIT

    def test_name_is_bandit(self) -> None:
        agent = BanditAgent()
        assert agent.name == "bandit"

    def test_default_cmd(self) -> None:
        agent = BanditAgent()
        assert "bandit" in agent.bandit_cmd[-1]

    def test_custom_cmd_and_timeout(self) -> None:
        agent = BanditAgent(bandit_cmd=["custom-bandit"], timeout=45)
        assert agent.bandit_cmd == ["custom-bandit"]
        assert agent.timeout == 45


class TestBanditSeverityMapping:
    def test_high_maps_to_critical(self) -> None:
        assert _map_bandit_severity("HIGH") == Severity.CRITICAL

    def test_medium_maps_to_warning(self) -> None:
        assert _map_bandit_severity("MEDIUM") == Severity.WARNING

    def test_low_maps_to_info(self) -> None:
        assert _map_bandit_severity("LOW") == Severity.INFO

    def test_case_insensitive_and_unknown(self) -> None:
        assert _map_bandit_severity("high") == Severity.CRITICAL
        assert _map_bandit_severity("UNKNOWN") == Severity.INFO


class TestBanditOutputParsing:
    def test_empty_output_returns_empty_list(self) -> None:
        agent = BanditAgent()
        assert agent.parse_bandit_output("") == []
        assert agent.parse_bandit_output("   ") == []

    def test_invalid_json_returns_empty_list(self) -> None:
        agent = BanditAgent()
        assert agent.parse_bandit_output("Not valid JSON") == []

    def test_valid_json_parsed(self) -> None:
        agent = BanditAgent()
        sample_report = json.dumps(
            {
                "results": [
                    {
                        "code": "1 eval(cmd)\n",
                        "filename": "src/dangerous.py",
                        "issue_severity": "HIGH",
                        "issue_text": "Use of possibly insecure function eval()",
                        "line_number": 1,
                        "test_id": "B307",
                        "more_info": "https://bandit.readthedocs.io/test/b307",
                    }
                ]
            }
        )
        findings = agent.parse_bandit_output(sample_report)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.file == "src/dangerous.py"
        assert finding.line == 1
        assert finding.rule_id == "B307"
        assert finding.message == "Use of possibly insecure function eval()"
        assert finding.category == Category.SECURITY
        assert finding.agent == AgentType.BANDIT
        assert finding.severity == Severity.CRITICAL
        assert finding.suggestion is not None
        assert "eval" in finding.suggestion

    def test_diff_filtering_in_parsing(self) -> None:
        agent = BanditAgent()
        sample_report = json.dumps(
            {
                "results": [
                    {
                        "filename": "src/app.py",
                        "issue_severity": "LOW",
                        "issue_text": "Issue on line 5",
                        "line_number": 5,
                        "test_id": "B101",
                    },
                    {
                        "filename": "src/app.py",
                        "issue_severity": "HIGH",
                        "issue_text": "Issue on line 20",
                        "line_number": 20,
                        "test_id": "B608",
                    },
                ]
            }
        )

        findings = agent.parse_bandit_output(sample_report, added_lines=frozenset({20}))
        assert len(findings) == 1
        assert findings[0].line == 20
        assert findings[0].rule_id == "B608"


class TestBanditReview:
    def test_review_sample_security_fixture(self) -> None:
        repo_root = Path(__file__).parent.parent
        agent = BanditAgent(repo_root=repo_root)
        fixture_path = "tests/fixtures/sample_security.py"

        diff_file = DiffFile(
            source_file=f"a/{fixture_path}",
            target_file=f"b/{fixture_path}",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=32,
                    target_start=1,
                    target_length=32,
                    lines=(
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="os.system(...)",
                            target_line=19,
                        ),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="subprocess.run(..., shell=True)",
                            target_line=20,
                        ),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="query = ...",
                            target_line=30,
                        ),
                    ),
                ),
            ),
        )

        findings = agent.review([diff_file])
        assert len(findings) >= 2
        rule_ids = {f.rule_id for f in findings}
        assert "B605" in rule_ids or "B602" in rule_ids or "B608" in rule_ids
        for f in findings:
            assert f.file == fixture_path
            assert f.line in {19, 20, 30}
            assert f.category == Category.SECURITY
            assert f.agent == AgentType.BANDIT

    def test_review_skips_non_python_files(self) -> None:
        agent = BanditAgent()
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
        agent = BanditAgent()
        diff_file = DiffFile(
            source_file="a/missing.py",
            target_file="b/missing.py",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=1,
                    target_start=1,
                    target_length=1,
                    lines=(DiffLine(line_type=LineType.ADDED, content="x = 1", target_line=1),),
                ),
            ),
        )
        findings = agent.review([diff_file])
        assert findings == []

    @patch("subprocess.run")
    def test_timeout_handled_gracefully(self, mock_run) -> None:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["bandit"], timeout=10)
        agent = BanditAgent()
        findings = agent.run_bandit(__file__)
        assert findings == []

    @patch("subprocess.run")
    def test_file_not_found_handled_gracefully(self, mock_run) -> None:
        mock_run.side_effect = FileNotFoundError("Bandit not found")
        agent = BanditAgent()
        findings = agent.run_bandit(__file__)
        assert findings == []
