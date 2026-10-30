from pathlib import Path

from code_review.agents.ast_agent import ASTAgent
from code_review.models.enums import AgentType, Category, Severity
from code_review.parsers.diff_parser import DiffFile, DiffHunk, DiffLine, LineType


class TestASTAgentInit:
    def test_agent_type_is_ast(self) -> None:
        agent = ASTAgent()
        assert agent.agent_type == AgentType.AST

    def test_name_is_ast(self) -> None:
        agent = ASTAgent()
        assert agent.name == "ast"

    def test_default_thresholds(self) -> None:
        agent = ASTAgent()
        assert agent.max_complexity == 10
        assert agent.max_depth == 4
        assert agent.max_function_lines == 50

    def test_custom_thresholds(self) -> None:
        agent = ASTAgent(
            repo_root=Path("."),
            max_complexity=5,
            max_depth=2,
            max_function_lines=20,
        )
        assert agent.max_complexity == 5
        assert agent.max_depth == 2
        assert agent.max_function_lines == 20


class TestASTAgentComplexity:
    def test_simple_function_no_findings(self) -> None:
        agent = ASTAgent()
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        findings = agent.analyze_source(code)
        assert len(findings) == 0

    def test_high_complexity_flagged(self) -> None:
        agent = ASTAgent(max_complexity=3)
        code = """def complex_logic(x: int) -> str:
    if x > 10:
        return "high"
    elif x > 5:
        return "mid"
    elif x > 0:
        return "low"
    else:
        return "zero"
"""
        findings = agent.analyze_source(code)
        complexity_findings = [f for f in findings if f.rule_id == "AST001"]
        assert len(complexity_findings) == 1
        finding = complexity_findings[0]
        assert finding.line == 1
        assert finding.severity == Severity.WARNING
        assert finding.category == Category.CODE_QUALITY
        assert finding.agent == AgentType.AST
        assert "cyclomatic complexity" in finding.message
        assert finding.suggestion is not None


class TestASTAgentNesting:
    def test_shallow_nesting_no_findings(self) -> None:
        agent = ASTAgent(max_depth=3)
        code = """def shallow(items: list[int]) -> list[int]:
    out = []
    for x in items:
        if x > 0:
            out.append(x)
    return out
"""
        findings = agent.analyze_source(code)
        nesting_findings = [f for f in findings if f.rule_id == "AST002"]
        assert len(nesting_findings) == 0

    def test_deep_nesting_flagged(self) -> None:
        agent = ASTAgent(max_depth=2)
        code = """def deeply_nested() -> None:
    for i in range(10):
        if i > 0:
            for j in range(5):
                print(j)
"""
        findings = agent.analyze_source(code)
        nesting_findings = [f for f in findings if f.rule_id == "AST002"]
        assert len(nesting_findings) == 1
        finding = nesting_findings[0]
        assert finding.line == 4
        assert finding.severity == Severity.WARNING
        assert finding.category == Category.CODE_QUALITY
        assert "nested too deeply" in finding.message


class TestASTAgentFunctionLength:
    def test_short_function_no_findings(self) -> None:
        agent = ASTAgent(max_function_lines=10)
        code = "def short_fn() -> None:\n    pass\n"
        findings = agent.analyze_source(code)
        length_findings = [f for f in findings if f.rule_id == "AST003"]
        assert len(length_findings) == 0

    def test_long_function_flagged(self) -> None:
        agent = ASTAgent(max_function_lines=5)
        code = """def long_fn() -> int:
    a = 1
    b = 2
    c = 3
    d = 4
    e = 5
    return a + b + c + d + e
"""
        findings = agent.analyze_source(code)
        length_findings = [f for f in findings if f.rule_id == "AST003"]
        assert len(length_findings) == 1
        finding = length_findings[0]
        assert finding.line == 1
        assert finding.severity == Severity.WARNING
        assert finding.category == Category.CODE_QUALITY
        assert "too long" in finding.message


class TestASTAgentWildcardImport:
    def test_specific_import_no_findings(self) -> None:
        agent = ASTAgent()
        code = "from math import sqrt, pi\n"
        findings = agent.analyze_source(code)
        wildcard_findings = [f for f in findings if f.rule_id == "AST004"]
        assert len(wildcard_findings) == 0

    def test_wildcard_import_flagged(self) -> None:
        agent = ASTAgent()
        code = "from math import *\n"
        findings = agent.analyze_source(code)
        wildcard_findings = [f for f in findings if f.rule_id == "AST004"]
        assert len(wildcard_findings) == 1
        finding = wildcard_findings[0]
        assert finding.line == 1
        assert finding.severity == Severity.WARNING
        assert finding.category == Category.BEST_PRACTICE
        assert "Wildcard import" in finding.message


class TestASTAgentSyntaxError:
    def test_syntax_error_reported(self) -> None:
        agent = ASTAgent()
        code = "def broken(:\n    pass\n"
        findings = agent.analyze_source(code)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule_id == "AST000"
        assert finding.severity == Severity.ERROR
        assert finding.category == Category.BUG_RISK
        assert "syntax error" in finding.message.lower()


class TestASTAgentDiffFiltering:
    def test_finding_on_added_line_retained(self) -> None:
        agent = ASTAgent()
        code = "from math import *\n"
        findings = agent.analyze_source(code, added_lines=frozenset({1}))
        assert len(findings) == 1

    def test_finding_on_untouched_line_filtered_out(self) -> None:
        agent = ASTAgent()
        code = "from math import *\n"
        findings = agent.analyze_source(code, added_lines=frozenset({10, 11}))
        assert len(findings) == 0


class TestASTAgentReview:
    def test_review_sample_complex_fixture(self) -> None:
        repo_root = Path(__file__).parent.parent
        agent = ASTAgent(repo_root=repo_root)
        fixture_path = "tests/fixtures/sample_complex.py"

        diff_file = DiffFile(
            source_file=f"a/{fixture_path}",
            target_file=f"b/{fixture_path}",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=100,
                    target_start=1,
                    target_length=120,
                    lines=(
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="from math import *",
                            target_line=6,
                        ),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="def calculate_discount",
                            target_line=9,
                        ),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="if val % 2 == 0:",
                            target_line=49,
                        ),
                        DiffLine(
                            line_type=LineType.ADDED,
                            content="def overly_long_function",
                            target_line=54,
                        ),
                    ),
                ),
            ),
        )

        findings = agent.review([diff_file])
        rule_ids = {f.rule_id for f in findings}
        assert "AST004" in rule_ids
        assert "AST001" in rule_ids
        assert "AST002" in rule_ids
        assert "AST003" in rule_ids
        for f in findings:
            assert f.file == fixture_path

    def test_review_skips_non_python_files(self) -> None:
        agent = ASTAgent()
        diff_file = DiffFile(
            source_file="a/README.md",
            target_file="b/README.md",
            hunks=(
                DiffHunk(
                    source_start=1,
                    source_length=1,
                    target_start=1,
                    target_length=1,
                    lines=(DiffLine(line_type=LineType.ADDED, content="# Header", target_line=1),),
                ),
            ),
        )
        findings = agent.review([diff_file])
        assert findings == []

    def test_review_skips_nonexistent_file(self) -> None:
        agent = ASTAgent()
        diff_file = DiffFile(
            source_file="a/does_not_exist.py",
            target_file="b/does_not_exist.py",
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
