from __future__ import annotations

import ast
import hashlib
import logging
from typing import Any

from code_review.cache.keys import compute_diff_hash
from code_review.parsers.diff_parser import DiffFile, LineType

logger = logging.getLogger(__name__)


class ASTNormalizer(ast.NodeTransformer):
    def __init__(self, strip_docstrings: bool = True) -> None:
        super().__init__()
        self.strip_docstrings = strip_docstrings

    def visit(self, node: ast.AST) -> Any:
        for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
            if hasattr(node, attr):
                setattr(node, attr, 0)
        return super().visit(node)

    def _strip_body_docstring(self, body: list[ast.stmt]) -> list[ast.stmt]:
        if not self.strip_docstrings or not body:
            return body

        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                return body[1:]
        return body

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node


def normalize_ast(tree: ast.AST, *, strip_docstrings: bool = True) -> ast.AST:
    normalizer = ASTNormalizer(strip_docstrings=strip_docstrings)
    return normalizer.visit(tree)


def compute_ast_hash(code: str, *, strip_docstrings: bool = True) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    normalized = normalize_ast(tree, strip_docstrings=strip_docstrings)
    dumped = ast.dump(normalized, annotate_fields=False, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def is_semantically_identical(
    code_a: str,
    code_b: str,
    *,
    strip_docstrings: bool = True,
) -> bool:
    hash_a = compute_ast_hash(code_a, strip_docstrings=strip_docstrings)
    hash_b = compute_ast_hash(code_b, strip_docstrings=strip_docstrings)

    if hash_a is not None and hash_b is not None:
        return hash_a == hash_b

    return code_a.strip() == code_b.strip()


def compute_diff_semantic_hash(
    diff_files: list[DiffFile],
    fallback_raw_diff: str = "",
) -> str:
    if not diff_files:
        return compute_diff_hash(fallback_raw_diff)

    file_hashes: list[str] = []

    for file in sorted(diff_files, key=lambda f: f.path):
        added_lines: list[str] = []
        for hunk in file.hunks:
            for line in hunk.lines:
                if line.line_type == LineType.ADDED:
                    added_lines.append(line.content)

        if not added_lines:
            continue

        code_snippet = "\n".join(added_lines)
        ast_hash = compute_ast_hash(code_snippet)

        if ast_hash is not None:
            file_hashes.append(f"{file.path}:ast:{ast_hash}")
        else:
            normalized_text = "\n".join(ln.rstrip() for ln in added_lines).strip()
            line_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
            file_hashes.append(f"{file.path}:lines:{line_hash}")

    if not file_hashes:
        return compute_diff_hash(fallback_raw_diff)

    combined = "|".join(file_hashes)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
