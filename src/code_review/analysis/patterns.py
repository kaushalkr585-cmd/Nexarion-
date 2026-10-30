from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from pathlib import Path

from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile, LineType

logger = logging.getLogger(__name__)


class PatternDetector:
    def __init__(self, diff_files: list[DiffFile], min_clone_lines: int = 4) -> None:
        self.diff_files = diff_files
        self.min_clone_lines = min_clone_lines

    def detect_code_clones(self) -> list[Finding]:
        findings: list[Finding] = []

        chunks: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

        for df in self.diff_files:
            if not df.path.endswith((".py", ".pyi", ".ts", ".tsx", ".js")):
                continue

            for hunk in df.hunks:
                added_lines = []
                for ln in hunk.lines:
                    text_str = ln.content.strip()
                    if (
                        ln.line_type == LineType.ADDED
                        and text_str
                        and not text_str.startswith(("#", "//", "/*", "*"))
                    ):
                        added_lines.append((ln.target_line or 1, text_str))

                if len(added_lines) < self.min_clone_lines:
                    continue

                keywords = ("def ", "class ", "if ", "for ", "while ", "try:", "async ")
                for i in range(len(added_lines) - self.min_clone_lines + 1):
                    window = added_lines[i : i + self.min_clone_lines]
                    start_line = window[0][0]

                    norm_text = "\n".join(w[1] for w in window)

                    if any(kw in norm_text for kw in keywords):
                        chunk_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
                        chunks[chunk_hash].append((df.path, start_line, norm_text))

        reported_clones: set[tuple[str, int]] = set()
        for chunk_instances in chunks.values():
            if len(chunk_instances) > 1:
                first_file, first_line, _ = chunk_instances[0]
                for other_file, other_line, _ in chunk_instances[1:]:
                    if (other_file, other_line) in reported_clones:
                        continue
                    reported_clones.add((other_file, other_line))

                    target_name = Path(first_file).name
                    findings.append(
                        Finding(
                            file=other_file,
                            line=other_line,
                            severity=Severity.WARNING,
                            category=Category.CODE_QUALITY,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f"Duplicate code block ({self.min_clone_lines}+ lines) detected: "
                                f"identical logic added here and in {target_name}:{first_line}."
                            ),
                            suggestion=(
                                "Extract the repeated logic into a reusable helper function "
                                "or utility module to follow DRY principles."
                            ),
                            rule_id="SEM007",
                        )
                    )

        return findings

    def detect_inconsistent_error_handling(self) -> list[Finding]:
        findings: list[Finding] = []

        for df in self.diff_files:
            if not df.path.endswith((".py", ".pyi")):
                continue

            added_lines_map = {
                ln.target_line: ln.content.strip()
                for ln in df.added_lines
                if ln.target_line is not None
            }

            for line_num, text in added_lines_map.items():
                if text == "except:" or text.startswith("except:"):
                    findings.append(
                        Finding(
                            file=df.path,
                            line=line_num,
                            severity=Severity.WARNING,
                            category=Category.BEST_PRACTICE,
                            agent=AgentType.SEMANTIC,
                            message=(
                                "Bare 'except:' clause catches all exceptions including "
                                "SystemExit and KeyboardInterrupt."
                            ),
                            suggestion=(
                                "Catch specific exceptions (e.g. 'except (KeyError, ValueError):')"
                                " instead of bare 'except:'."
                            ),
                            rule_id="SEM008",
                        )
                    )

                elif "except Exception:" in text or "except BaseException:" in text:
                    next_line_text = added_lines_map.get(line_num + 1, "")
                    if next_line_text == "pass" or "pass" in text:
                        findings.append(
                            Finding(
                                file=df.path,
                                line=line_num,
                                severity=Severity.WARNING,
                                category=Category.BEST_PRACTICE,
                                agent=AgentType.SEMANTIC,
                                message=(
                                    "Silently swallowed exception ('except Exception: pass') "
                                    "hides bugs and prevents debugging."
                                ),
                                suggestion=(
                                    "Log the exception with traceback or handle the error "
                                    "gracefully."
                                ),
                                rule_id="SEM008",
                            )
                        )

        return findings

    def detect_repeated_magic_constants(self) -> list[Finding]:
        findings: list[Finding] = []

        literal_occurrences: dict[str, list[tuple[str, int]]] = defaultdict(list)

        for df in self.diff_files:
            if not df.path.endswith((".py", ".pyi", ".ts", ".tsx", ".js")):
                continue

            for hunk in df.hunks:
                for line in hunk.added_lines:
                    text = line.content.strip()
                    line_num = line.target_line or 1

                    import re

                    matches = re.findall(r'["\']([^"\']{6,})["\']', text)
                    for lit in matches:
                        prefixes = (
                            "%",
                            "http",
                            "SELECT ",
                            "INSERT ",
                            "UPDATE ",
                            "DELETE ",
                            "Bearer ",
                            "/api/",
                        )
                        if lit.startswith(prefixes):
                            literal_occurrences[lit].append((df.path, line_num))
                        elif " " in lit and len(lit) >= 12:
                            literal_occurrences[lit].append((df.path, line_num))

        reported_constants: set[tuple[str, int]] = set()
        for lit, occurrences in literal_occurrences.items():
            unique_files = {occ[0] for occ in occurrences}
            if len(unique_files) >= 2:
                first_file, first_line = occurrences[0]
                for file_path, line_num in occurrences[1:]:
                    if (file_path, line_num) in reported_constants:
                        continue
                    reported_constants.add((file_path, line_num))

                    preview = lit[:30] + "..." if len(lit) > 30 else lit
                    findings.append(
                        Finding(
                            file=file_path,
                            line=line_num,
                            severity=Severity.INFO,
                            category=Category.CODE_QUALITY,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f'Repeated magic constant "{preview}" is duplicated across '
                                f"multiple files (also in {Path(first_file).name}:{first_line})."
                            ),
                            suggestion=(
                                "Extract this repeated literal into a centralized constant or "
                                "environment configuration variable."
                            ),
                            rule_id="SEM009",
                        )
                    )
        return findings
