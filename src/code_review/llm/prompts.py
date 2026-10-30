from __future__ import annotations

import json
import logging
from typing import Any

from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile, LineType

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """You are a senior engineer performing a rigorous review on a Git PR diff.

Your goal is to catch subtle semantic bugs and architectural risks that linters miss:
1. Logic errors, off-by-one errors, inverse conditional checks.
2. Unhandled edge cases (e.g. empty lists, None values, zero division, missing keys).
3. Resource leaks (unclosed files, network handles, database connections).
4. Mutable default arguments or unexpected state mutations.
5. Concurrency hazards or race conditions.
6. Silent exception swallowing or incorrect error handling.

DO NOT report:
- Code style, formatting, whitespace, or line length (Ruff handles this).
- Missing docstrings or comments unless critical logic is ambiguous.
- Import ordering or unused imports.
- Issues in unchanged context lines (lines starting with ' ').

RULES:
- ONLY report issues on ADDED lines (prefixed with '+').
- Provide the exact line number from the '+' lines.
- Be concise, actionable, and constructive.
- Suggest a concrete code fix in the 'suggestion' field whenever possible.

You MUST respond with valid JSON matching this exact structure:
{
  "findings": [
    {
      "line": 42,
      "rule_id": "LOGIC001",
      "message": "Clear explanation of the problem.",
      "severity": "error",
      "category": "bug_risk",
      "suggestion": "replacement code or fix"
    }
  ]
}

Valid severity values: "info", "warning", "error", "critical"
Valid category values: "security", "code_quality", "performance",
                       "documentation", "bug_risk", "best_practice"
If no issues are found, return: {"findings": []}
"""


def format_diff_for_review(diff_file: DiffFile) -> str:
    lines_output: list[str] = [
        f"File: {diff_file.path}",
        "Review the following changes:",
        "----------------------------------------",
    ]

    for hunk_idx, hunk in enumerate(diff_file.hunks, 1):
        target_end = hunk.target_start + hunk.target_length
        lines_output.append(
            f"@@ Hunk {hunk_idx} (target lines {hunk.target_start} to {target_end}) @@"
        )
        for line in hunk.lines:
            if line.line_type == LineType.ADDED:
                prefix = "+"
                ln_str = f"{line.target_line:>5} " if line.target_line is not None else "    + "
            elif line.line_type == LineType.REMOVED:
                prefix = "-"
                ln_str = "    - "
            else:
                prefix = " "
                ln_str = f"{line.target_line:>5} " if line.target_line is not None else "      "

            lines_output.append(f"{ln_str}{prefix} {line.content}")

    lines_output.append("----------------------------------------")
    added_lines_list = sorted(diff_file.added_line_numbers)
    lines_output.append(f"Added lines eligible for review in {diff_file.path}: {added_lines_list}")

    if len(diff_file.hunks) >= 2:
        from code_review.analysis.multi_hunk import MultiHunkAnalyzer

        mh_summary = MultiHunkAnalyzer(diff_file).generate_context_summary()
        if mh_summary:
            lines_output.append("")
            lines_output.append(mh_summary)

    return "\n".join(lines_output)


def parse_llm_findings(
    raw_response: str,
    diff_file: DiffFile,
) -> list[Finding]:
    if not raw_response or not raw_response.strip():
        return []

    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Failed to decode LLM JSON response for %s: %s (raw text: %.100s)",
            diff_file.path,
            exc,
            raw_response,
        )
        return []

    raw_items: list[dict[str, Any]] = []
    if isinstance(data, dict):
        raw_items = data.get("findings", [])
        if not isinstance(raw_items, list):
            raw_items = []
    elif isinstance(data, list):
        raw_items = data

    findings: list[Finding] = []
    allowed_lines = diff_file.added_line_numbers

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        raw_line = item.get("line")
        if not isinstance(raw_line, int):
            try:
                raw_line = int(raw_line)
            except (TypeError, ValueError):
                logger.debug("Discarding LLM finding with invalid line: %s", item)
                continue

        if raw_line not in allowed_lines:
            logger.debug(
                "Discarding LLM finding on line %d not in added lines for %s",
                raw_line,
                diff_file.path,
            )
            continue

        message = str(item.get("message", "")).strip()
        if not message:
            continue

        raw_sev = str(item.get("severity", "warning")).lower().strip()
        severity = _normalize_severity(raw_sev)

        raw_cat = str(item.get("category", "bug_risk")).lower().strip()
        category = _normalize_category(raw_cat)

        rule_id = item.get("rule_id")
        if rule_id is not None:
            rule_id = str(rule_id).strip() or None

        suggestion = item.get("suggestion")
        if suggestion is not None:
            suggestion = str(suggestion).strip() or None

        try:
            finding = Finding(
                file=diff_file.path,
                line=raw_line,
                rule_id=rule_id,
                message=message,
                severity=severity,
                category=category,
                agent=AgentType.LLM,
                suggestion=suggestion,
            )
            findings.append(finding)
        except Exception as exc:
            logger.warning("Failed to construct Finding from LLM output: %s", exc)

    return findings


def _normalize_severity(val: str) -> Severity:
    mapping = {
        "info": Severity.INFO,
        "informational": Severity.INFO,
        "low": Severity.INFO,
        "warning": Severity.WARNING,
        "warn": Severity.WARNING,
        "medium": Severity.WARNING,
        "error": Severity.ERROR,
        "high": Severity.ERROR,
        "critical": Severity.CRITICAL,
    }
    return mapping.get(val, Severity.WARNING)


def _normalize_category(val: str) -> Category:
    mapping = {
        "security": Category.SECURITY,
        "code_quality": Category.CODE_QUALITY,
        "quality": Category.CODE_QUALITY,
        "style": Category.CODE_QUALITY,
        "performance": Category.PERFORMANCE,
        "perf": Category.PERFORMANCE,
        "documentation": Category.DOCUMENTATION,
        "docs": Category.DOCUMENTATION,
        "bug_risk": Category.BUG_RISK,
        "bug": Category.BUG_RISK,
        "logic": Category.BUG_RISK,
        "best_practice": Category.BEST_PRACTICE,
        "convention": Category.BEST_PRACTICE,
    }
    return mapping.get(val, Category.BUG_RISK)
