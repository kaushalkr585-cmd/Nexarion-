from pathlib import Path

import pytest

from code_review.parsers.diff_parser import (
    DiffFile,
    DiffLine,
    LineType,
    parse_diff,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_diff_text() -> str:
    return (FIXTURES_DIR / "sample.diff").read_text(encoding="utf-8")


@pytest.fixture
def multi_file_diff_text() -> str:
    return (FIXTURES_DIR / "multi_file.diff").read_text(encoding="utf-8")


@pytest.fixture
def parsed_sample(sample_diff_text: str) -> list[DiffFile]:
    return parse_diff(sample_diff_text)


@pytest.fixture
def parsed_multi(multi_file_diff_text: str) -> list[DiffFile]:
    return parse_diff(multi_file_diff_text)


class TestParseDiffBasic:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_diff("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert parse_diff("   \n\n  ") == []

    def test_sample_diff_returns_one_file(self, parsed_sample: list[DiffFile]) -> None:
        assert len(parsed_sample) == 1

    def test_multi_file_diff_returns_two_files(self, parsed_multi: list[DiffFile]) -> None:
        assert len(parsed_multi) == 2


class TestDiffFile:
    def test_file_path_strips_prefix(self, parsed_sample: list[DiffFile]) -> None:
        assert parsed_sample[0].path == "src/auth.py"

    def test_source_and_target_files(self, parsed_sample: list[DiffFile]) -> None:
        diff_file = parsed_sample[0]
        assert diff_file.source_file == "a/src/auth.py"
        assert diff_file.target_file == "b/src/auth.py"

    def test_multi_file_paths(self, parsed_multi: list[DiffFile]) -> None:
        paths = [f.path for f in parsed_multi]
        assert "src/utils.py" in paths
        assert "README.md" in paths

    def test_is_rename_default_false(self, parsed_sample: list[DiffFile]) -> None:
        assert parsed_sample[0].is_rename is False

    def test_added_lines_across_hunks(self, parsed_sample: list[DiffFile]) -> None:
        diff_file = parsed_sample[0]
        added = diff_file.added_lines

        assert len(added) > 0
        assert all(line.line_type == LineType.ADDED for line in added)

    def test_removed_lines_across_hunks(self, parsed_sample: list[DiffFile]) -> None:
        diff_file = parsed_sample[0]
        removed = diff_file.removed_lines
        assert len(removed) > 0
        assert all(line.line_type == LineType.REMOVED for line in removed)

    def test_added_line_numbers(self, parsed_sample: list[DiffFile]) -> None:
        diff_file = parsed_sample[0]
        numbers = diff_file.added_line_numbers
        assert isinstance(numbers, frozenset)
        assert len(numbers) > 0

        assert all(n > 0 for n in numbers)

    def test_diff_file_is_frozen(self, parsed_sample: list[DiffFile]) -> None:
        with pytest.raises(Exception):
            parsed_sample[0].source_file = "modified"  # type: ignore[misc]


class TestDiffHunk:
    def test_sample_has_two_hunks(self, parsed_sample: list[DiffFile]) -> None:
        assert len(parsed_sample[0].hunks) == 2

    def test_hunk_has_start_and_length(self, parsed_sample: list[DiffFile]) -> None:
        first_hunk = parsed_sample[0].hunks[0]
        assert first_hunk.source_start >= 1
        assert first_hunk.source_length >= 0
        assert first_hunk.target_start >= 1
        assert first_hunk.target_length >= 0

    def test_hunk_added_lines(self, parsed_sample: list[DiffFile]) -> None:
        first_hunk = parsed_sample[0].hunks[0]
        added = first_hunk.added_lines
        assert all(ln.line_type == LineType.ADDED for ln in added)

    def test_hunk_removed_lines(self, parsed_sample: list[DiffFile]) -> None:
        first_hunk = parsed_sample[0].hunks[0]
        removed = first_hunk.removed_lines
        assert all(ln.line_type == LineType.REMOVED for ln in removed)


class TestDiffLine:
    def test_line_types_present(self, parsed_sample: list[DiffFile]) -> None:
        all_lines = []
        for hunk in parsed_sample[0].hunks:
            all_lines.extend(hunk.lines)
        types_found = {ln.line_type for ln in all_lines}
        assert LineType.ADDED in types_found
        assert LineType.REMOVED in types_found
        assert LineType.CONTEXT in types_found

    def test_added_line_has_target_number(self, parsed_sample: list[DiffFile]) -> None:
        added = parsed_sample[0].added_lines
        first_added = added[0]
        assert first_added.target_line is not None
        assert first_added.source_line is None

    def test_removed_line_has_source_number(self, parsed_sample: list[DiffFile]) -> None:
        removed = parsed_sample[0].removed_lines
        first_removed = removed[0]
        assert first_removed.source_line is not None
        assert first_removed.target_line is None

    def test_context_line_has_both_numbers(self, parsed_sample: list[DiffFile]) -> None:
        all_lines = []
        for hunk in parsed_sample[0].hunks:
            all_lines.extend(hunk.lines)
        context_lines = [ln for ln in all_lines if ln.line_type == LineType.CONTEXT]
        assert len(context_lines) > 0
        for ctx in context_lines:
            assert ctx.source_line is not None
            assert ctx.target_line is not None

    def test_line_content_no_prefix(self, parsed_sample: list[DiffFile]) -> None:
        added = parsed_sample[0].added_lines
        for line in added:
            assert not line.content.startswith("+")
            assert not line.content.startswith("-")

    def test_diff_line_is_frozen(self) -> None:
        line = DiffLine(
            line_type=LineType.ADDED,
            content="test",
            target_line=1,
        )
        with pytest.raises(Exception):
            line.content = "modified"  # type: ignore[misc]


class TestLineType:
    def test_values(self) -> None:
        assert LineType.ADDED == "added"
        assert LineType.REMOVED == "removed"
        assert LineType.CONTEXT == "context"

    def test_is_str_enum(self) -> None:
        assert isinstance(LineType.ADDED, str)


class TestParseDiffInline:
    def test_single_line_addition(self) -> None:
        diff = (
            "--- a/hello.py\n"
            "+++ b/hello.py\n"
            "@@ -1,2 +1,3 @@\n"
            " existing line\n"
            "+new line\n"
            " another existing line\n"
        )
        files = parse_diff(diff)
        assert len(files) == 1
        assert len(files[0].added_lines) == 1
        assert files[0].added_lines[0].content == "new line"

    def test_single_line_removal(self) -> None:
        diff = (
            "--- a/hello.py\n"
            "+++ b/hello.py\n"
            "@@ -1,3 +1,2 @@\n"
            " existing line\n"
            "-removed line\n"
            " another existing line\n"
        )
        files = parse_diff(diff)
        assert len(files) == 1
        assert len(files[0].removed_lines) == 1
        assert files[0].removed_lines[0].content == "removed line"

    def test_resilient_fallback_parsing(self) -> None:
        diff = (
            "--- a/auth_service.py\n"
            "+++ b/auth_service.py\n"
            "@@ -15,4 +15,6 @@ def verify_credentials(user, password):\n"
            "-    return password_hasher.check(password, user.stored_hash)\n"
            "+    if password == 'master':\n"
            "+        return True\n"
        )
        files = parse_diff(diff)
        assert len(files) == 1
        assert len(files[0].added_lines) == 2
        assert len(files[0].removed_lines) == 1
