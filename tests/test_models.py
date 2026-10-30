from datetime import UTC

import pytest
from pydantic import ValidationError

from code_review.models.enums import (
    AgentType,
    Category,
    Severity,
    severity_rank,
)
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult


class TestSeverity:
    def test_all_values_exist(self) -> None:
        assert Severity.INFO == "info"
        assert Severity.WARNING == "warning"
        assert Severity.ERROR == "error"
        assert Severity.CRITICAL == "critical"

    def test_is_str_enum(self) -> None:
        assert isinstance(Severity.INFO, str)
        assert f"Level: {Severity.WARNING}" == "Level: warning"

    def test_severity_rank_ordering(self) -> None:
        assert severity_rank(Severity.INFO) < severity_rank(Severity.WARNING)
        assert severity_rank(Severity.WARNING) < severity_rank(Severity.ERROR)
        assert severity_rank(Severity.ERROR) < severity_rank(Severity.CRITICAL)

    def test_severity_from_string(self) -> None:
        assert Severity("info") is Severity.INFO
        assert Severity("critical") is Severity.CRITICAL

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(ValueError, match="'banana' is not a valid Severity"):
            Severity("banana")


class TestCategory:
    def test_all_values_exist(self) -> None:
        expected = {
            "security",
            "code_quality",
            "performance",
            "documentation",
            "bug_risk",
            "best_practice",
        }
        actual = {c.value for c in Category}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(Category.SECURITY, str)
        assert Category.SECURITY == "security"


class TestAgentType:
    def test_all_values_exist(self) -> None:
        expected = {"ast", "ruff", "bandit", "llm", "semantic"}
        actual = {a.value for a in AgentType}
        assert actual == expected


class TestFinding:
    def _make_finding(self, **overrides) -> Finding:
        defaults = {
            "file": "src/auth.py",
            "line": 42,
            "severity": Severity.WARNING,
            "category": Category.SECURITY,
            "agent": AgentType.BANDIT,
            "message": "Possible SQL injection",
        }
        defaults.update(overrides)
        return Finding(**defaults)

    def test_valid_finding_creation(self) -> None:
        finding = self._make_finding()
        assert finding.file == "src/auth.py"
        assert finding.line == 42
        assert finding.severity == Severity.WARNING
        assert finding.category == Category.SECURITY
        assert finding.agent == AgentType.BANDIT
        assert finding.message == "Possible SQL injection"

    def test_optional_fields_default_to_none(self) -> None:
        finding = self._make_finding()
        assert finding.suggestion is None
        assert finding.rule_id is None

    def test_optional_fields_can_be_set(self) -> None:
        finding = self._make_finding(
            suggestion="Use parameterized queries",
            rule_id="B608",
        )
        assert finding.suggestion == "Use parameterized queries"
        assert finding.rule_id == "B608"

    def test_finding_is_frozen(self) -> None:
        finding = self._make_finding()
        with pytest.raises(ValidationError):
            finding.line = 99  # type: ignore[misc]

    def test_line_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            self._make_finding(line=0)
        with pytest.raises(ValidationError):
            self._make_finding(line=-5)

    def test_message_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            self._make_finding(message="")

    def test_invalid_severity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make_finding(severity="banana")

    def test_finding_serialization(self) -> None:
        finding = self._make_finding(rule_id="B608")
        data = finding.model_dump()
        assert data["file"] == "src/auth.py"
        assert data["severity"] == "warning"
        assert data["rule_id"] == "B608"

    def test_finding_json_round_trip(self) -> None:
        original = self._make_finding(suggestion="Fix it", rule_id="E501")
        json_str = original.model_dump_json()
        restored = Finding.model_validate_json(json_str)
        assert restored == original


class TestReviewResult:
    def _make_finding(self, severity: Severity = Severity.WARNING, **kw) -> Finding:
        defaults = {
            "file": "test.py",
            "line": 1,
            "severity": severity,
            "category": Category.CODE_QUALITY,
            "agent": AgentType.AST,
            "message": "Test finding",
        }
        defaults.update(kw)
        return Finding(**defaults)

    def test_empty_review(self) -> None:
        result = ReviewResult()
        assert result.total_findings == 0
        assert result.has_critical is False
        assert result.files_reviewed == 0

    def test_total_findings_computed(self) -> None:
        findings = [self._make_finding() for _ in range(3)]
        result = ReviewResult(findings=findings)
        assert result.total_findings == 3

    def test_has_critical_true(self) -> None:
        findings = [
            self._make_finding(severity=Severity.INFO),
            self._make_finding(severity=Severity.CRITICAL),
        ]
        result = ReviewResult(findings=findings)
        assert result.has_critical is True

    def test_has_critical_false(self) -> None:
        findings = [
            self._make_finding(severity=Severity.WARNING),
            self._make_finding(severity=Severity.ERROR),
        ]
        result = ReviewResult(findings=findings)
        assert result.has_critical is False

    def test_findings_by_severity(self) -> None:
        findings = [
            self._make_finding(severity=Severity.INFO),
            self._make_finding(severity=Severity.WARNING),
            self._make_finding(severity=Severity.WARNING),
            self._make_finding(severity=Severity.CRITICAL),
        ]
        result = ReviewResult(findings=findings)
        counts = result.findings_by_severity
        assert counts["info"] == 1
        assert counts["warning"] == 2
        assert counts["error"] == 0
        assert counts["critical"] == 1

    def test_sorted_findings_default(self) -> None:
        findings = [
            self._make_finding(severity=Severity.INFO),
            self._make_finding(severity=Severity.CRITICAL),
            self._make_finding(severity=Severity.WARNING),
        ]
        result = ReviewResult(findings=findings)
        sorted_f = result.sorted_findings()
        assert sorted_f[0].severity == Severity.CRITICAL
        assert sorted_f[-1].severity == Severity.INFO

    def test_sorted_findings_ascending(self) -> None:
        findings = [
            self._make_finding(severity=Severity.CRITICAL),
            self._make_finding(severity=Severity.INFO),
        ]
        result = ReviewResult(findings=findings)
        sorted_f = result.sorted_findings(reverse=False)
        assert sorted_f[0].severity == Severity.INFO
        assert sorted_f[-1].severity == Severity.CRITICAL

    def test_created_at_is_utc(self) -> None:
        result = ReviewResult()
        assert result.created_at.tzinfo is not None
        assert result.created_at.tzinfo == UTC

    def test_review_result_serialization(self) -> None:
        findings = [self._make_finding()]
        result = ReviewResult(findings=findings, files_reviewed=2, review_time_ms=500)
        data = result.model_dump()
        assert data["total_findings"] == 1
        assert data["files_reviewed"] == 2
        assert data["review_time_ms"] == 500
        assert "created_at" in data

    def test_files_reviewed_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ReviewResult(files_reviewed=-1)
