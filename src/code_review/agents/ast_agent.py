import ast
import logging
from pathlib import Path

from code_review.agents.base import BaseAgent
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile

logger = logging.getLogger(__name__)

NESTING_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)


def _calculate_complexity(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    complexity = 1

    for child in ast.iter_child_nodes(func_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        complexity += _count_decision_points(child)

    return complexity


def _count_decision_points(node: ast.AST) -> int:
    count = 0

    if isinstance(node, (ast.If, ast.IfExp)):
        count += 1
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        count += 1
    elif isinstance(node, ast.While):
        count += 1
    elif isinstance(node, ast.ExceptHandler):
        count += 1
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        count += 1
    elif isinstance(node, ast.Assert):
        count += 1
    elif isinstance(node, ast.BoolOp):
        count += len(node.values) - 1
    elif isinstance(node, ast.Match):
        count += len(node.cases)

    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            count += _count_decision_points(child)

    return count


class _ASTAnalysisVisitor(ast.NodeVisitor):
    def __init__(
        self,
        file_path: str,
        max_complexity: int,
        max_depth: int,
        max_function_lines: int,
    ) -> None:
        self.file_path = file_path
        self.max_complexity = max_complexity
        self.max_depth = max_depth
        self.max_function_lines = max_function_lines
        self.findings: list[Finding] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                module_name = node.module or "module"
                self.findings.append(
                    Finding(
                        file=self.file_path,
                        line=node.lineno,
                        severity=Severity.WARNING,
                        category=Category.BEST_PRACTICE,
                        agent=AgentType.AST,
                        message=(
                            f"Wildcard import 'from {module_name} import *' pollutes namespace"
                        ),
                        suggestion=(
                            "Explicitly import only the specific names required "
                            f"from '{module_name}'."
                        ),
                        rule_id="AST004",
                    )
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)
        self.generic_visit(node)

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        complexity = _calculate_complexity(node)
        if complexity > self.max_complexity:
            self.findings.append(
                Finding(
                    file=self.file_path,
                    line=node.lineno,
                    severity=Severity.WARNING,
                    category=Category.CODE_QUALITY,
                    agent=AgentType.AST,
                    message=(
                        f"Function '{node.name}' has cyclomatic complexity of {complexity} "
                        f"(exceeds threshold of {self.max_complexity})"
                    ),
                    suggestion=(
                        "Refactor this function into smaller, single-purpose helper functions "
                        "to reduce branching complexity."
                    ),
                    rule_id="AST001",
                )
            )

        end_lineno = getattr(node, "end_lineno", node.lineno)
        length = end_lineno - node.lineno + 1
        if length > self.max_function_lines:
            self.findings.append(
                Finding(
                    file=self.file_path,
                    line=node.lineno,
                    severity=Severity.WARNING,
                    category=Category.CODE_QUALITY,
                    agent=AgentType.AST,
                    message=(
                        f"Function '{node.name}' is too long ({length} lines, "
                        f"exceeds threshold of {self.max_function_lines})"
                    ),
                    suggestion="Break this function into smaller, focused helper functions.",
                    rule_id="AST003",
                )
            )

        self._check_nesting(node.body, current_depth=0)

    def _check_nesting(self, statements: list[ast.stmt], current_depth: int) -> None:
        for stmt in statements:
            if isinstance(stmt, NESTING_NODE_TYPES):
                new_depth = current_depth + 1
                if new_depth > self.max_depth:
                    self.findings.append(
                        Finding(
                            file=self.file_path,
                            line=stmt.lineno,
                            severity=Severity.WARNING,
                            category=Category.CODE_QUALITY,
                            agent=AgentType.AST,
                            message=(
                                f"Block nested too deeply (depth {new_depth}, "
                                f"exceeds maximum of {self.max_depth})"
                            ),
                            suggestion=(
                                "Reduce nesting depth by using guard clauses, early returns, "
                                "or extracting helper functions."
                            ),
                            rule_id="AST002",
                        )
                    )

                for child_stmts in self._get_compound_bodies(stmt):
                    self._check_nesting(child_stmts, new_depth)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

    @staticmethod
    def _get_compound_bodies(stmt: ast.AST) -> list[list[ast.stmt]]:
        bodies: list[list[ast.stmt]] = []
        if hasattr(stmt, "body") and isinstance(stmt.body, list):
            bodies.append(stmt.body)
        if hasattr(stmt, "orelse") and isinstance(stmt.orelse, list):
            bodies.append(stmt.orelse)
        if hasattr(stmt, "finalbody") and isinstance(stmt.finalbody, list):
            bodies.append(stmt.finalbody)
        if hasattr(stmt, "handlers") and isinstance(stmt.handlers, list):
            for handler in stmt.handlers:
                if isinstance(handler, ast.ExceptHandler) and isinstance(handler.body, list):
                    bodies.append(handler.body)
        return bodies


class ASTAgent(BaseAgent):
    def __init__(
        self,
        repo_root: Path | str | None = None,
        max_complexity: int = 10,
        max_depth: int = 4,
        max_function_lines: int = 50,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
        self.max_complexity = max_complexity
        self.max_depth = max_depth
        self.max_function_lines = max_function_lines

    @property
    def agent_type(self) -> AgentType:
        return AgentType.AST

    def analyze_source(
        self,
        source_code: str,
        file_path: str = "snippet.py",
        added_lines: set[int] | frozenset[int] | None = None,
    ) -> list[Finding]:
        clean_path = file_path.replace("\\", "/")
        try:
            tree = ast.parse(source_code, filename=clean_path)
        except SyntaxError as e:
            logger.warning("Syntax error in %s at line %s: %s", clean_path, e.lineno, e.msg)
            err_line = e.lineno or 1
            if added_lines is None or err_line in added_lines:
                return [
                    Finding(
                        file=clean_path,
                        line=err_line,
                        severity=Severity.ERROR,
                        category=Category.BUG_RISK,
                        agent=AgentType.AST,
                        message=f"Python syntax error: {e.msg}",
                        suggestion="Fix syntax error to ensure valid Python code.",
                        rule_id="AST000",
                    )
                ]
            return []

        visitor = _ASTAnalysisVisitor(
            file_path=clean_path,
            max_complexity=self.max_complexity,
            max_depth=self.max_depth,
            max_function_lines=self.max_function_lines,
        )
        visitor.visit(tree)

        if added_lines is not None:
            return [f for f in visitor.findings if f.line in added_lines]
        return visitor.findings

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        findings: list[Finding] = []

        for diff_file in diff_files:
            file_path = diff_file.path

            if not file_path.endswith((".py", ".pyi")):
                logger.debug("Skipping non-Python file for AST review: %s", file_path)
                continue

            full_path = (self.repo_root / file_path).resolve()
            if not full_path.is_file():
                logger.debug("File does not exist on disk, skipping AST review: %s", full_path)
                continue

            try:
                source_code = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError as err:
                logger.warning("Failed to read file %s: %s", full_path, err)
                continue

            file_findings = self.analyze_source(
                source_code=source_code,
                file_path=file_path,
                added_lines=diff_file.added_line_numbers,
            )
            findings.extend(file_findings)
        return findings
