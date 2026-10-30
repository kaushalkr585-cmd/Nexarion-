from __future__ import annotations

import ast

from code_review.analysis.ast_hasher import (
    compute_ast_hash,
    compute_diff_semantic_hash,
    is_semantically_identical,
    normalize_ast,
)
from code_review.parsers.diff_parser import parse_diff


class TestASTNormalizer:
    def test_strip_positions(self) -> None:
        tree = ast.parse("x = 10\ny = 20")
        norm = normalize_ast(tree)
        for node in ast.walk(norm):
            if hasattr(node, "lineno"):
                assert node.lineno == 0

    def test_strip_docstrings(self) -> None:
        code_with_doc = (
            '"""Module docstring."""\ndef foo():\n    """Function docstring."""\n    return 42\n'
        )
        code_without_doc = "def foo():\n    return 42\n"

        h1 = compute_ast_hash(code_with_doc, strip_docstrings=True)
        h2 = compute_ast_hash(code_without_doc, strip_docstrings=True)
        assert h1 == h2


class TestASTSemanticHashing:
    def test_comments_and_blank_lines_ignored(self) -> None:
        code_a = "def calculate(x, y):\n    return x + y\n"
        code_b = (
            "# This is a helper function\n\n"
            "def calculate(x, y):\n"
            "    # Add numbers together\n"
            "    return x + y\n\n"
        )
        assert is_semantically_identical(code_a, code_b)
        assert compute_ast_hash(code_a) == compute_ast_hash(code_b)

    def test_logic_changes_produce_different_hash(self) -> None:
        code_add = "def calc(x, y): return x + y"
        code_sub = "def calc(x, y): return x - y"
        assert not is_semantically_identical(code_add, code_sub)
        assert compute_ast_hash(code_add) != compute_ast_hash(code_sub)

    def test_syntax_error_returns_none(self) -> None:
        invalid_code = "def unclosed_syntax(:"
        assert compute_ast_hash(invalid_code) is None

    def test_diff_semantic_hash_on_diff_files(self) -> None:
        diff_a = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,1 +1,3 @@\n"
            "+def add(a, b):\n"
            "+    return a + b\n"
        )
        diff_b = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,1 +1,5 @@\n"
            "+# Added comment\n"
            "+def add(a, b):\n"
            "+    # Inside comment\n"
            "+    return a + b\n"
        )
        files_a = parse_diff(diff_a)
        files_b = parse_diff(diff_b)

        hash_a = compute_diff_semantic_hash(files_a, fallback_raw_diff=diff_a)
        hash_b = compute_diff_semantic_hash(files_b, fallback_raw_diff=diff_b)
        assert hash_a == hash_b
