from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile, LineType

logger = logging.getLogger(__name__)

RESOURCE_ACQUIRE_CALLS = {"open", "acquire", "connect", "Socket", "socket", "lock"}
RESOURCE_RELEASE_CALLS = {"close", "release", "disconnect"}


@dataclass
class HunkScopeInfo:
    hunk_index: int
    target_start: int
    target_end: int
    added_lines: list[int] = field(default_factory=list)
    enclosing_scopes: list[str] = field(default_factory=list)
    acquired_resources: list[tuple[str, int]] = field(default_factory=list)
    released_resources: list[tuple[str, int]] = field(default_factory=list)
    exit_statements: list[int] = field(default_factory=list)
    defined_variables: list[tuple[str, int]] = field(default_factory=list)


class MultiHunkAnalyzer:
    def __init__(self, diff_file: DiffFile, source_code: str | None = None) -> None:
        self.diff_file = diff_file
        self.source_code = source_code or self._reconstruct_target_source(diff_file)
        self.hunks = diff_file.hunks
        self._parsed_tree: ast.AST | None = None
        self._parse_tree()

    def _parse_tree(self) -> None:
        if not self.source_code.strip():
            return
        try:
            self._parsed_tree = ast.parse(self.source_code, filename=self.diff_file.path)
        except SyntaxError:
            self._parsed_tree = None

    @staticmethod
    def _reconstruct_target_source(diff_file: DiffFile) -> str:
        lines: list[str] = []
        for hunk in diff_file.hunks:
            for line in hunk.lines:
                if line.line_type in (LineType.ADDED, LineType.CONTEXT):
                    lines.append(line.content)
        return "\n".join(lines)

    def build_hunk_scopes(self) -> list[HunkScopeInfo]:
        hunk_infos: list[HunkScopeInfo] = []

        for idx, hunk in enumerate(self.hunks):
            added_nums = [ln.target_line for ln in hunk.added_lines if ln.target_line is not None]
            h_info = HunkScopeInfo(
                hunk_index=idx,
                target_start=hunk.target_start,
                target_end=hunk.target_start + hunk.target_length,
                added_lines=added_nums,
            )

            for line in hunk.added_lines:
                target_line = line.target_line or 1
                text = line.content.strip()

                if text.startswith(("return", "raise ", "raise\n", "sys.exit")):
                    h_info.exit_statements.append(target_line)

                for acq in RESOURCE_ACQUIRE_CALLS:
                    if f".{acq}(" in text or f"={acq}(" in text or f"= {acq}(" in text:
                        parts = text.split("=")[0].strip()
                        var_name = parts.split(".")[-1] if "." in parts else parts
                        h_info.acquired_resources.append((var_name, target_line))

                for rel in RESOURCE_RELEASE_CALLS:
                    if f".{rel}(" in text:
                        parts = text.split(f".{rel}")[0].strip()
                        var_name = parts.split(".")[-1]
                        h_info.released_resources.append((var_name, target_line))

                if "=" in text and not text.startswith(("#", "if ", "while ", "assert ")):
                    left = text.split("=")[0].strip()
                    if left.isidentifier():
                        h_info.defined_variables.append((left, target_line))

            hunk_infos.append(h_info)

        return hunk_infos

    def check_cross_hunk_resource_leaks(self) -> list[Finding]:
        findings: list[Finding] = []
        if len(self.hunks) < 2:
            return findings

        scopes = self.build_hunk_scopes()
        acquired_so_far: dict[str, int] = {}
        released_so_far: set[str] = set()

        for s in scopes:
            for res_name, line_num in s.acquired_resources:
                acquired_so_far[res_name] = line_num

            for res_name, _ in s.released_resources:
                released_so_far.add(res_name)

            if s.exit_statements and acquired_so_far:
                for res_name, acq_line in acquired_so_far.items():
                    if res_name not in released_so_far and res_name.isidentifier():
                        exit_line = s.exit_statements[0]
                        findings.append(
                            Finding(
                                file=self.diff_file.path,
                                line=exit_line,
                                severity=Severity.ERROR,
                                category=Category.BUG_RISK,
                                agent=AgentType.SEMANTIC,
                                message=(
                                    f"Resource '{res_name}' acquired in earlier hunk "
                                    f"(line {acq_line}) may leak on exit at line {exit_line}."
                                ),
                                suggestion=(
                                    f"Refactor to use 'with', or call '{res_name}.close()' / "
                                    f"'{res_name}.release()' before returning."
                                ),
                                rule_id="SEM005",
                            )
                        )

        return findings

    def check_cross_hunk_variable_collisions(self) -> list[Finding]:
        findings: list[Finding] = []
        if len(self.hunks) < 2:
            return findings

        scopes = self.build_hunk_scopes()
        seen_vars: dict[str, int] = {}

        for s in scopes:
            for var_name, line_num in s.defined_variables:
                if var_name in ("_", "i", "j", "k", "idx", "item", "e", "err"):
                    continue

                if var_name in seen_vars:
                    prev_line = seen_vars[var_name]
                    hunk_num = s.hunk_index + 1
                    findings.append(
                        Finding(
                            file=self.diff_file.path,
                            line=line_num,
                            severity=Severity.WARNING,
                            category=Category.BUG_RISK,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f"Variable '{var_name}' in Hunk {hunk_num} (line {line_num}) "
                                f"shadows previous assignment at line {prev_line}."
                            ),
                            suggestion=(
                                f"Use a distinct identifier for '{var_name}' to "
                                "prevent scope confusion across hunks."
                            ),
                            rule_id="SEM006",
                        )
                    )
                else:
                    seen_vars[var_name] = line_num

        return findings

    def generate_context_summary(self) -> str:
        if len(self.hunks) < 2:
            return ""

        file_name = Path(self.diff_file.path).name
        summary_lines = [f"### Multi-Hunk Context for `{file_name}` ({len(self.hunks)} hunks):"]
        scopes = self.build_hunk_scopes()
        for s in scopes:
            added_cnt = len(s.added_lines)
            summary_lines.append(
                f"- **Hunk {s.hunk_index + 1}** (lines {s.target_start}–{s.target_end}): "
                f"+{added_cnt} lines modified. "
            )
        return "\n".join(summary_lines)
