from __future__ import annotations

import logging
from pathlib import Path

from code_review.agents.base import BaseAgent
from code_review.analysis.dependency_graph import DependencyGraph
from code_review.analysis.multi_hunk import MultiHunkAnalyzer
from code_review.analysis.patterns import PatternDetector
from code_review.analysis.symbol_table import FileSymbolTable, build_file_symbol_table
from code_review.models.enums import AgentType
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile, LineType

logger = logging.getLogger(__name__)


class SemanticAgent(BaseAgent):
    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        min_clone_lines: int = 4,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
        self.min_clone_lines = min_clone_lines

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SEMANTIC

    def _get_file_content(self, diff_file: DiffFile) -> str:
        full_path = (self.repo_root / diff_file.path).resolve()
        if full_path.is_file():
            try:
                return full_path.read_text(encoding="utf-8", errors="replace")
            except OSError as err:
                logger.debug("Could not read %s from disk: %s", full_path, err)

        lines: list[str] = []
        for hunk in diff_file.hunks:
            for line in hunk.lines:
                if line.line_type in (LineType.ADDED, LineType.CONTEXT):
                    lines.append(line.content)
        return "\n".join(lines)

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        if not diff_files:
            return []

        findings: list[Finding] = []
        file_tables: dict[str, FileSymbolTable] = {}
        added_lines_by_file: dict[str, frozenset[int]] = {}

        for df in diff_files:
            clean_path = df.path
            added_lines_by_file[clean_path] = df.added_line_numbers

            if clean_path.endswith((".py", ".pyi")):
                source = self._get_file_content(df)
                file_tables[clean_path] = build_file_symbol_table(source, clean_path)

        if file_tables:
            dep_graph = DependencyGraph(file_tables, repo_root=self.repo_root)
            findings.extend(dep_graph.check_circular_dependencies())
            findings.extend(dep_graph.check_broken_imports())
            findings.extend(dep_graph.check_call_signatures())
            findings.extend(dep_graph.check_unused_exports())

        for df in diff_files:
            if len(df.hunks) >= 2 and df.path.endswith((".py", ".pyi")):
                source = self._get_file_content(df)
                mh_analyzer = MultiHunkAnalyzer(df, source_code=source)
                findings.extend(mh_analyzer.check_cross_hunk_resource_leaks())
                findings.extend(mh_analyzer.check_cross_hunk_variable_collisions())

        pattern_detector = PatternDetector(diff_files, min_clone_lines=self.min_clone_lines)
        findings.extend(pattern_detector.detect_code_clones())
        findings.extend(pattern_detector.detect_inconsistent_error_handling())
        findings.extend(pattern_detector.detect_repeated_magic_constants())

        filtered_findings: list[Finding] = []
        for f in findings:
            valid_lines = added_lines_by_file.get(f.file, frozenset())
            if not valid_lines:
                continue

            if f.line in valid_lines:
                filtered_findings.append(f)
            else:
                if f.line == 1 or min(valid_lines) <= f.line <= max(valid_lines):
                    closest = min(valid_lines, key=lambda ln: abs(ln - f.line))
                    adjusted = Finding(
                        file=f.file,
                        line=closest,
                        severity=f.severity,
                        category=f.category,
                        agent=self.agent_type,
                        message=f.message,
                        suggestion=f.suggestion,
                        rule_id=f.rule_id,
                    )
                    filtered_findings.append(adjusted)

        logger.debug(
            "SemanticAgent found %d issues across %d files",
            len(filtered_findings),
            len(diff_files),
        )
        return filtered_findings
CrossFileAgent = SemanticAgent
