import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from code_review.agents.base import BaseAgent
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile

logger = logging.getLogger(__name__)


def _map_ruff_category(code: str) -> Category:
    code_upper = code.upper()

    if code_upper.startswith("S"):
        return Category.SECURITY
    if code_upper.startswith(("F", "B", "A")):
        return Category.BUG_RISK
    if code_upper.startswith("PERF"):
        return Category.PERFORMANCE
    if code_upper.startswith("D"):
        return Category.DOCUMENTATION
    if code_upper.startswith(("E", "W", "I", "N", "UP", "C4", "SIM")):
        return Category.CODE_QUALITY

    return Category.CODE_QUALITY


def _map_ruff_severity(code: str, raw_severity: str = "") -> Severity:
    code_upper = code.upper()

    if code_upper.startswith(("E9", "F821", "F822", "F823")):
        return Severity.ERROR

    if code_upper.startswith("S"):
        return Severity.ERROR

    if code_upper.startswith(("I", "D", "UP", "W")):
        return Severity.INFO

    return Severity.WARNING


class RuffAgent(BaseAgent):
    def __init__(
        self,
        repo_root: Path | str | None = None,
        ruff_cmd: list[str] | str | None = None,
        timeout: int = 30,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
        self.timeout = timeout

        if ruff_cmd is None:
            self.ruff_cmd: list[str] = [sys.executable, "-m", "ruff"]
        elif isinstance(ruff_cmd, str):
            self.ruff_cmd = [ruff_cmd]
        else:
            self.ruff_cmd = list(ruff_cmd)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RUFF

    def parse_ruff_output(
        self,
        output_json: str,
        added_lines: set[int] | frozenset[int] | None = None,
        fallback_file: str = "",
    ) -> list[Finding]:
        if not output_json or not output_json.strip():
            return []

        try:
            diagnostics: list[dict[str, Any]] = json.loads(output_json)
        except json.JSONDecodeError as err:
            logger.warning("Failed to parse Ruff JSON output: %s", err)
            return []

        findings: list[Finding] = []

        for item in diagnostics:
            location = item.get("location") or {}
            line = location.get("row")
            if not line or line < 1:
                continue

            if added_lines is not None and line not in added_lines:
                continue

            raw_filename = item.get("filename") or fallback_file
            if os.path.isabs(raw_filename):
                try:
                    rel_file = os.path.relpath(raw_filename, self.repo_root)
                except ValueError:
                    rel_file = raw_filename
            else:
                rel_file = raw_filename
            clean_file = rel_file.replace("\\", "/")

            code = item.get("code") or "RUFF"
            message = item.get("message") or "Linter diagnostic reported."

            fix_data = item.get("fix")
            suggestion = fix_data.get("message") if isinstance(fix_data, dict) else None

            severity = _map_ruff_severity(code, item.get("severity", ""))
            category = _map_ruff_category(code)

            findings.append(
                Finding(
                    file=clean_file,
                    line=line,
                    severity=severity,
                    category=category,
                    agent=AgentType.RUFF,
                    message=message,
                    suggestion=suggestion,
                    rule_id=code,
                )
            )

        return findings

    def run_ruff(
        self,
        target_path: Path | str,
        added_lines: set[int] | frozenset[int] | None = None,
    ) -> list[Finding]:
        resolved_path = Path(target_path)
        if not resolved_path.is_absolute():
            resolved_path = (self.repo_root / resolved_path).resolve()

        if not resolved_path.is_file():
            logger.debug("Ruff target file does not exist: %s", resolved_path)
            return []

        cmd = [
            *self.ruff_cmd,
            "check",
            "--output-format",
            "json",
            "--exit-zero",
            str(resolved_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Ruff check timed out after %s seconds on %s", self.timeout, resolved_path
            )
            return []
        except FileNotFoundError as err:
            logger.error("Ruff executable not found (%s): %s", self.ruff_cmd, err)
            return []

        return self.parse_ruff_output(
            output_json=result.stdout,
            added_lines=added_lines,
            fallback_file=str(target_path),
        )

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        findings: list[Finding] = []

        for diff_file in diff_files:
            file_path = diff_file.path

            if not file_path.endswith((".py", ".pyi")):
                logger.debug("Skipping non-Python file for Ruff review: %s", file_path)
                continue

            full_path = (self.repo_root / file_path).resolve()
            if not full_path.is_file():
                logger.debug("File does not exist on disk, skipping Ruff review: %s", full_path)
                continue

            file_findings = self.run_ruff(
                target_path=full_path,
                added_lines=diff_file.added_line_numbers,
            )

            adjusted_findings = [
                f.model_copy(update={"file": diff_file.path}) if f.file != diff_file.path else f
                for f in file_findings
            ]
            findings.extend(adjusted_findings)
        return findings
