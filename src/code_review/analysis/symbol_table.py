from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParameterDef:
    name: str
    has_default: bool = False
    default_repr: str | None = None
    annotation: str | None = None
    kind: str = "POSITIONAL_OR_KEYWORD"


@dataclass(frozen=True)
class SymbolDef:
    name: str
    kind: str
    file: str
    line: int
    end_line: int
    parameters: tuple[ParameterDef, ...] = field(default_factory=tuple)
    return_annotation: str | None = None
    docstring: str | None = None
    parent: str | None = None
    is_exported: bool = True


@dataclass(frozen=True)
class SymbolCall:
    name: str
    caller: str | None
    file: str
    line: int
    args_count: int
    kwargs_names: tuple[str, ...] = field(default_factory=tuple)
    has_varargs: bool = False
    has_varkwargs: bool = False


@dataclass(frozen=True)
class ImportDef:
    module: str
    imported_name: str
    alias: str | None = None
    file: str = ""
    line: int = 1
    level: int = 0
    is_wildcard: bool = False


@dataclass
class FileSymbolTable:
    file_path: str
    symbols: dict[str, SymbolDef] = field(default_factory=dict)
    imports: list[ImportDef] = field(default_factory=list)
    calls: list[SymbolCall] = field(default_factory=list)
    all_exports: list[str] | None = None

    def get_symbol(self, name: str) -> SymbolDef | None:
        return self.symbols.get(name)

    def is_publicly_exported(self, name: str) -> bool:
        if self.all_exports is not None:
            return name in self.all_exports
        return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def _unparse_node(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.symbols: dict[str, SymbolDef] = {}
        self.imports: list[ImportDef] = []
        self.calls: list[SymbolCall] = []
        self.all_exports: list[str] | None = None
        self._current_scope: list[str] = []

    def _get_current_caller(self) -> str | None:
        return self._current_scope[-1] if self._current_scope else None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportDef(
                    module=alias.name,
                    imported_name=alias.name,
                    alias=alias.asname,
                    file=self.file_path,
                    line=node.lineno,
                    level=0,
                    is_wildcard=False,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = node.level or 0
        for alias in node.names:
            is_wildcard = alias.name == "*"
            self.imports.append(
                ImportDef(
                    module=module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    file=self.file_path,
                    line=node.lineno,
                    level=level,
                    is_wildcard=is_wildcard,
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        in_class = self._current_scope and self._current_scope[-1].startswith("class:")
        parent_class = self._get_current_caller() if in_class else None
        parent_name = parent_class.replace("class:", "") if parent_class else None
        kind = "method" if parent_name else ("async_function" if is_async else "function")

        params = self._extract_parameters(node.args)
        ret_anno = _unparse_node(node.returns)
        doc = ast.get_docstring(node)

        symbol_key = f"{parent_name}.{node.name}" if parent_name else node.name
        is_exported = not node.name.startswith("_") or (
            node.name.startswith("__") and node.name.endswith("__")
        )

        self.symbols[symbol_key] = SymbolDef(
            name=node.name,
            kind=kind,
            file=self.file_path,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parameters=tuple(params),
            return_annotation=ret_anno,
            docstring=doc,
            parent=parent_name,
            is_exported=is_exported,
        )

        scope_name = f"func:{symbol_key}"
        self._current_scope.append(scope_name)
        self.generic_visit(node)
        self._current_scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        doc = ast.get_docstring(node)
        self.symbols[node.name] = SymbolDef(
            name=node.name,
            kind="class",
            file=self.file_path,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parameters=(),
            return_annotation=None,
            docstring=doc,
            parent=None,
            is_exported=not node.name.startswith("_"),
        )

        scope_name = f"class:{node.name}"
        self._current_scope.append(scope_name)
        self.generic_visit(node)
        self._current_scope.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self._current_scope:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        exports: list[str] = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exports.append(elt.value)
                        self.all_exports = exports
                elif isinstance(target, ast.Name):
                    val_repr = _unparse_node(node.value)
                    kind = "constant" if target.id.isupper() else "variable"
                    self.symbols[target.id] = SymbolDef(
                        name=target.id,
                        kind=kind,
                        file=self.file_path,
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        docstring=None,
                        return_annotation=val_repr,
                        is_exported=not target.id.startswith("_"),
                    )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target_name = _unparse_node(node.func) or "unknown"
        has_varargs = any(isinstance(arg, ast.Starred) for arg in node.args)
        has_varkwargs = any(kw.arg is None for kw in node.keywords)
        kwargs_names = tuple(kw.arg for kw in node.keywords if kw.arg is not None)

        self.calls.append(
            SymbolCall(
                name=target_name,
                caller=self._get_current_caller(),
                file=self.file_path,
                line=node.lineno,
                args_count=len(node.args),
                kwargs_names=kwargs_names,
                has_varargs=has_varargs,
                has_varkwargs=has_varkwargs,
            )
        )
        self.generic_visit(node)

    def _extract_parameters(self, args: ast.arguments) -> list[ParameterDef]:
        params: list[ParameterDef] = []

        posonly_count = len(args.posonlyargs)

        std_count = len(args.args)
        total_pos = posonly_count + std_count

        defaults = args.defaults
        num_defaults = len(defaults)
        default_offset = total_pos - num_defaults

        idx = 0
        for arg in args.posonlyargs:
            has_def = idx >= default_offset
            def_node = defaults[idx - default_offset] if has_def else None
            params.append(
                ParameterDef(
                    name=arg.arg,
                    has_default=has_def,
                    default_repr=_unparse_node(def_node),
                    annotation=_unparse_node(arg.annotation),
                    kind="POSITIONAL_ONLY",
                )
            )
            idx += 1

        for arg in args.args:
            has_def = idx >= default_offset
            def_node = defaults[idx - default_offset] if has_def else None
            params.append(
                ParameterDef(
                    name=arg.arg,
                    has_default=has_def,
                    default_repr=_unparse_node(def_node),
                    annotation=_unparse_node(arg.annotation),
                    kind="POSITIONAL_OR_KEYWORD",
                )
            )
            idx += 1

        if args.vararg:
            params.append(
                ParameterDef(
                    name=args.vararg.arg,
                    has_default=False,
                    annotation=_unparse_node(args.vararg.annotation),
                    kind="VAR_POSITIONAL",
                )
            )

        for kw_arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
            has_def = kw_default is not None
            params.append(
                ParameterDef(
                    name=kw_arg.arg,
                    has_default=has_def,
                    default_repr=_unparse_node(kw_default) if has_def else None,
                    annotation=_unparse_node(kw_arg.annotation),
                    kind="KEYWORD_ONLY",
                )
            )

        if args.kwarg:
            params.append(
                ParameterDef(
                    name=args.kwarg.arg,
                    has_default=False,
                    annotation=_unparse_node(args.kwarg.annotation),
                    kind="VAR_KEYWORD",
                )
            )

        return params


def build_file_symbol_table(source_code: str, file_path: str = "snippet.py") -> FileSymbolTable:
    clean_path = file_path.replace("\\", "/")
    table = FileSymbolTable(file_path=clean_path)
    if not source_code or not source_code.strip():
        return table

    try:
        tree = ast.parse(source_code, filename=clean_path)
    except SyntaxError as exc:
        logger.debug("Syntax error parsing %s for symbol table: %s", clean_path, exc)
        return table

    visitor = _SymbolVisitor(clean_path)
    visitor.visit(tree)

    table.symbols = visitor.symbols
    table.imports = visitor.imports
    table.calls = visitor.calls
    table.all_exports = visitor.all_exports
    return table
