from enum import StrEnum

from pydantic import BaseModel, Field, computed_field
from unidiff import PatchSet


class LineType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CONTEXT = "context"


class DiffLine(BaseModel):
    model_config = {"frozen": True}

    line_type: LineType = Field(
        ...,
        description="Whether this line was added, removed, or unchanged.",
    )
    content: str = Field(
        ...,
        description="The text content of the line (without +/- prefix).",
    )
    source_line: int | None = Field(
        default=None,
        description="Line number in the old file.  None for added lines.",
    )
    target_line: int | None = Field(
        default=None,
        description="Line number in the new file.  None for removed lines.",
    )


class DiffHunk(BaseModel):
    model_config = {"frozen": True}

    source_start: int = Field(..., description="Starting line number in the old file.")
    source_length: int = Field(..., description="Number of old-file lines in this hunk.")
    target_start: int = Field(..., description="Starting line number in the new file.")
    target_length: int = Field(..., description="Number of new-file lines in this hunk.")
    lines: tuple[DiffLine, ...] = Field(
        default_factory=tuple,
        description="All lines in this hunk, in order.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def added_lines(self) -> tuple[DiffLine, ...]:
        return tuple(ln for ln in self.lines if ln.line_type == LineType.ADDED)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def removed_lines(self) -> tuple[DiffLine, ...]:
        return tuple(ln for ln in self.lines if ln.line_type == LineType.REMOVED)


class DiffFile(BaseModel):
    model_config = {"frozen": True}

    source_file: str = Field(..., description="File path in the old version.")
    target_file: str = Field(..., description="File path in the new version.")
    is_rename: bool = Field(
        default=False,
        description="True if the file was renamed between old and new.",
    )
    hunks: tuple[DiffHunk, ...] = Field(
        default_factory=tuple,
        description="All hunks of changes for this file.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def path(self) -> str:
        raw = self.target_file if self.target_file != "/dev/null" else self.source_file

        for prefix in ("b/", "a/"):
            if raw.startswith(prefix):
                return raw[2:]
        return raw

    @computed_field  # type: ignore[prop-decorator]
    @property
    def added_lines(self) -> tuple[DiffLine, ...]:
        result: list[DiffLine] = []
        for hunk in self.hunks:
            result.extend(hunk.added_lines)
        return tuple(result)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def removed_lines(self) -> tuple[DiffLine, ...]:
        result: list[DiffLine] = []
        for hunk in self.hunks:
            result.extend(hunk.removed_lines)
        return tuple(result)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def added_line_numbers(self) -> frozenset[int]:
        return frozenset(ln.target_line for ln in self.added_lines if ln.target_line is not None)


def _parse_diff_fallback(diff_text: str) -> list[DiffFile]:
    import re

    if not diff_text or not diff_text.strip():
        return []

    lines = diff_text.splitlines()
    files: list[DiffFile] = []
    curr_source = "a/file.py"
    curr_target = "b/file.py"
    curr_hunk_lines: list[DiffLine] = []
    curr_hunks: list[DiffHunk] = []
    target_line = 1
    source_line = 1
    hunk_start = 1

    def flush_hunk() -> None:
        nonlocal curr_hunk_lines, hunk_start
        if curr_hunk_lines:
            curr_hunks.append(
                DiffHunk(
                    source_start=hunk_start,
                    source_length=len(curr_hunk_lines),
                    target_start=hunk_start,
                    target_length=len(curr_hunk_lines),
                    lines=tuple(curr_hunk_lines),
                )
            )
            curr_hunk_lines = []

    def flush_file() -> None:
        nonlocal curr_hunks, curr_source, curr_target
        flush_hunk()
        if curr_hunks:
            files.append(
                DiffFile(
                    source_file=curr_source,
                    target_file=curr_target,
                    is_rename=False,
                    hunks=tuple(curr_hunks),
                )
            )
            curr_hunks = []

    has_diff_markers = any(
        line.startswith(("--- ", "+++ ", "diff --git ", "@@ ")) for line in lines
    )
    if not has_diff_markers:
        code_lines = [
            DiffLine(
                line_type=LineType.ADDED,
                content=line,
                source_line=None,
                target_line=i + 1,
            )
            for i, line in enumerate(lines)
        ]
        return [
            DiffFile(
                source_file="a/code.py",
                target_file="b/code.py",
                is_rename=False,
                hunks=(
                    DiffHunk(
                        source_start=1,
                        source_length=0,
                        target_start=1,
                        target_length=len(code_lines),
                        lines=tuple(code_lines),
                    ),
                ),
            )
        ]

    for line in lines:
        if line.startswith("diff --git "):
            flush_file()
            parts = line.split()
            if len(parts) >= 4:
                curr_source = parts[2].lstrip("a/")
                curr_target = parts[3].lstrip("b/")
        elif line.startswith("--- "):
            curr_source = line[4:].strip().lstrip("a/")
        elif line.startswith("+++ "):
            curr_target = line[4:].strip().lstrip("b/")
        elif line.startswith("@@"):
            flush_hunk()
            m = re.search(r"\+(\d+)", line)
            hunk_start = int(m.group(1)) if m else 1
            target_line = hunk_start
            source_line = hunk_start
        elif line.startswith("+"):
            curr_hunk_lines.append(
                DiffLine(
                    line_type=LineType.ADDED,
                    content=line[1:],
                    source_line=None,
                    target_line=target_line,
                )
            )
            target_line += 1
        elif line.startswith("-"):
            curr_hunk_lines.append(
                DiffLine(
                    line_type=LineType.REMOVED,
                    content=line[1:],
                    source_line=source_line,
                    target_line=None,
                )
            )
            source_line += 1
        else:
            clean = line[1:] if line.startswith(" ") else line
            curr_hunk_lines.append(
                DiffLine(
                    line_type=LineType.CONTEXT,
                    content=clean,
                    source_line=source_line,
                    target_line=target_line,
                )
            )
            source_line += 1
            target_line += 1

    flush_file()
    return files


def parse_diff(diff_text: str) -> list[DiffFile]:
    if not diff_text or not diff_text.strip():
        return []

    try:
        patch_set = PatchSet(diff_text)
        result: list[DiffFile] = []

        for patched_file in patch_set:
            hunks: list[DiffHunk] = []

            for hunk in patched_file:
                lines: list[DiffLine] = []

                for line in hunk:
                    if line.is_added:
                        line_type = LineType.ADDED
                    elif line.is_removed:
                        line_type = LineType.REMOVED
                    else:
                        line_type = LineType.CONTEXT

                    lines.append(
                        DiffLine(
                            line_type=line_type,
                            content=line.value.rstrip("\n"),
                            source_line=line.source_line_no,
                            target_line=line.target_line_no,
                        )
                    )

                hunks.append(
                    DiffHunk(
                        source_start=hunk.source_start,
                        source_length=hunk.source_length,
                        target_start=hunk.target_start,
                        target_length=hunk.target_length,
                        lines=tuple(lines),
                    )
                )

            result.append(
                DiffFile(
                    source_file=patched_file.source_file,
                    target_file=patched_file.target_file,
                    is_rename=patched_file.is_rename,
                    hunks=tuple(hunks),
                )
            )

        if result:
            return result
        return _parse_diff_fallback(diff_text)
    except Exception:
        return _parse_diff_fallback(diff_text)
