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

RECOMMENDATIONS: dict[str, str] = {
    "B105": (
        "Store credentials in environment variables or a secrets manager "
        "instead of hardcoding in source code."
    ),
    "B106": (
        "Do not hardcode passwords in function arguments or definitions; "
        "load from secure configuration."
    ),
    "B307": (
        "Use ast.literal_eval() or structured parsers (e.g., json.loads) "
        "instead of insecure eval()."
    ),
    "B602": (
        "Avoid subprocess calls with shell=True; pass command arguments as "
        "a list to avoid command injection."
    ),
    "B605": (
        "Avoid starting processes through a shell (os.system); use subprocess.run "
        "with argument vectors."
    ),
    "B608": (
        "Use parameterized queries or an ORM rather than string "
        "formatting/concatenation to prevent SQL injection."
    ),
    "B404": "Review subprocess invocations carefully to ensure inputs are strictly validated.",
}


def _map_bandit_severity(raw_severity: str) -> Severity:
    sev = raw_severity.strip().upper()
    if sev == "HIGH":
        return Severity.CRITICAL
    if sev == "MEDIUM":
        return Severity.WARNING
    return Severity.INFO


class BanditAgent(BaseAgent):
    def __init__(
        self,
        repo_root: Path | str | None = None,
        bandit_cmd: list[str] | str | None = None,
        timeout: int = 60,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
        self.timeout = timeout

        if bandit_cmd is None:
            self.bandit_cmd: list[str] = [sys.executable, "-m", "bandit"]
        elif isinstance(bandit_cmd, str):
            self.bandit_cmd = [bandit_cmd]
        else:
            self.bandit_cmd = list(bandit_cmd)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.BANDIT

    def parse_bandit_output(
        self,
        output_json: str,
        added_lines: set[int] | frozenset[int] | None = None,
        fallback_file: str = "",
    ) -> list[Finding]:
        if not output_json or not output_json.strip():
            return []

        try:
            report: dict[str, Any] = json.loads(output_json)
        except json.JSONDecodeError as err:
            logger.warning("Failed to parse Bandit JSON output: %s", err)
            return []

        results = report.get("results") or []
        findings: list[Finding] = []

        for item in results:
            line = item.get("line_number")
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

            test_id = item.get("test_id") or "BANDIT"
            issue_text = item.get("issue_text") or "Security vulnerability detected."
            severity = _map_bandit_severity(item.get("issue_severity", "LOW"))

            remediation = RECOMMENDATIONS.get(test_id)
            more_info = item.get("more_info")
            if remediation and more_info:
                suggestion = f"{remediation} (Ref: {more_info})"
            elif remediation:
                suggestion = remediation
            elif more_info:
                suggestion = f"See {more_info} for remediation details."
            else:
                suggestion = "Review code for potential security risks."

            findings.append(
                Finding(
                    file=clean_file,
                    line=line,
                    severity=severity,
                    category=Category.SECURITY,
                    agent=AgentType.BANDIT,
                    message=issue_text,
                    suggestion=suggestion,
                    rule_id=test_id,
                )
            )

        return findings

    def run_bandit(
        self,
        target_path: Path | str,
        added_lines: set[int] | frozenset[int] | None = None,
    ) -> list[Finding]:
        resolved_path = Path(target_path)
        if not resolved_path.is_absolute():
            resolved_path = (self.repo_root / resolved_path).resolve()

        if not resolved_path.is_file():
            logger.debug("Bandit target file does not exist: %s", resolved_path)
            return []

        cmd = [
            *self.bandit_cmd,
            "-f",
            "json",
            "-q",
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
                "Bandit scan timed out after %s seconds on %s", self.timeout, resolved_path
            )
            return []
        except FileNotFoundError as err:
            logger.error("Bandit executable not found (%s): %s", self.bandit_cmd, err)
            return []

        return self.parse_bandit_output(
            output_json=result.stdout,
            added_lines=added_lines,
            fallback_file=str(target_path),
        )

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        findings: list[Finding] = []

        for diff_file in diff_files:
            file_path = diff_file.path

            if not file_path.endswith((".py", ".pyi")):
                logger.debug("Skipping non-Python file for Bandit review: %s", file_path)
                continue

            full_path = (self.repo_root / file_path).resolve()
            if not full_path.is_file():
                logger.debug("File does not exist on disk, skipping Bandit review: %s", full_path)
                continue

            file_findings = self.run_bandit(
                target_path=full_path,
                added_lines=diff_file.added_line_numbers,
            )

            adjusted_findings = [
                f.model_copy(update={"file": diff_file.path}) if f.file != diff_file.path else f
                for f in file_findings
            ]
            findings.extend(adjusted_findings)
        return findings
