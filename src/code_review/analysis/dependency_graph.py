from __future__ import annotations

import logging
from pathlib import Path

from code_review.analysis.symbol_table import FileSymbolTable, ImportDef, SymbolDef
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding

logger = logging.getLogger(__name__)


class DependencyGraph:
    def __init__(
        self, file_tables: dict[str, FileSymbolTable], repo_root: Path | None = None
    ) -> None:
        self.file_tables = file_tables
        self.repo_root = repo_root or Path.cwd()

        self._module_to_file: dict[str, str] = {}
        self._build_module_map()

    def _build_module_map(self) -> None:
        for path in self.file_tables:
            clean_path = path.replace("\\", "/").lstrip("/")
            p = Path(clean_path)
            stem = p.stem
            self._module_to_file[stem] = path

            parts = p.with_suffix("").parts
            dotted = ".".join(parts)
            self._module_to_file[dotted] = path

            for prefix in ("src.", "app.", "lib."):
                if dotted.startswith(prefix):
                    self._module_to_file[dotted[len(prefix) :]] = path

    def resolve_module_file(self, source_file: str, imp: ImportDef) -> str | None:
        if imp.level > 0:
            source_dir = Path(source_file).parent
            target_dir = source_dir
            for _ in range(imp.level - 1):
                target_dir = target_dir.parent

            mod_stem = imp.module if imp.module else imp.imported_name
            candidate_parts = list(target_dir.parts)
            if mod_stem:
                candidate_parts.extend(mod_stem.split("."))

            candidate_rel = "/".join(candidate_parts).replace("\\", "/").lstrip("/")

            for ext in (".py", "/__init__.py"):
                attempt = (candidate_rel + ext).lstrip("/")
                for known_file in self.file_tables:
                    if known_file.endswith(attempt) or attempt.endswith(known_file):
                        return known_file

        mod = imp.module.strip() if imp.module else imp.imported_name.strip()
        if mod in self._module_to_file:
            return self._module_to_file[mod]

        last_part = mod.split(".")[-1]
        if last_part in self._module_to_file:
            return self._module_to_file[last_part]

        return None

    def check_circular_dependencies(self) -> list[Finding]:
        findings: list[Finding] = []
        adj: dict[str, set[str]] = {f: set() for f in self.file_tables}

        for file_path, table in self.file_tables.items():
            for imp in table.imports:
                target_file = self.resolve_module_file(file_path, imp)
                if target_file and target_file != file_path:
                    adj[file_path].add(target_file)

        visited: dict[str, int] = {}
        cycles: list[list[str]] = []

        def dfs(node: str, stack: list[str]) -> None:
            visited[node] = 1
            stack.append(node)
            for neighbor in adj.get(node, ()):
                if visited.get(neighbor) == 1:
                    cycle_start = stack.index(neighbor)
                    cycles.append(stack[cycle_start:] + [neighbor])
                elif visited.get(neighbor, 0) == 0:
                    dfs(neighbor, stack)
            stack.pop()
            visited[node] = 2

        for file_path in self.file_tables:
            if visited.get(file_path, 0) == 0:
                dfs(file_path, [])

        reported_pairs: set[tuple[str, str]] = set()
        for cycle in cycles:
            if len(cycle) >= 2:
                u, v = cycle[0], cycle[1]
                pair_key = tuple(sorted([u, v]))
                if pair_key in reported_pairs:
                    continue
                reported_pairs.add(pair_key)  # type: ignore[arg-type]

                culprit_line = 1
                table_u = self.file_tables.get(u)
                if table_u:
                    for imp in table_u.imports:
                        if self.resolve_module_file(u, imp) == v:
                            culprit_line = imp.line
                            break

                cycle_repr = " -> ".join(Path(p).name for p in cycle)
                findings.append(
                    Finding(
                        file=u,
                        line=culprit_line,
                        severity=Severity.WARNING,
                        category=Category.CODE_QUALITY,
                        agent=AgentType.SEMANTIC,
                        message=f"Circular dependency detected between modules: {cycle_repr}.",
                        suggestion=(
                            "Break circular import by refactoring shared models or types "
                            "into a standalone module, or using local function imports."
                        ),
                        rule_id="SEM001",
                    )
                )

        return findings

    def check_broken_imports(self) -> list[Finding]:
        findings: list[Finding] = []

        for file_path, table in self.file_tables.items():
            for imp in table.imports:
                if imp.is_wildcard or not imp.module:
                    continue

                target_file = self.resolve_module_file(file_path, imp)
                if not target_file or target_file == file_path:
                    continue

                target_table = self.file_tables.get(target_file)
                if not target_table:
                    continue

                symbol_name = imp.imported_name
                has_export = (
                    target_table.all_exports is not None
                    and symbol_name in target_table.all_exports
                )
                is_defined = symbol_name in target_table.symbols or has_export

                if not is_defined:
                    findings.append(
                        Finding(
                            file=file_path,
                            line=imp.line,
                            severity=Severity.ERROR,
                            category=Category.BUG_RISK,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f"Imported symbol '{symbol_name}' not found in target module "
                                f"'{Path(target_file).name}'."
                            ),
                            suggestion=(
                                f"Check symbol spelling or ensure '{symbol_name}' is exported "
                                f"in {Path(target_file).name}."
                            ),
                            rule_id="SEM002",
                        )
                    )

        return findings

    def check_call_signatures(self) -> list[Finding]:
        findings: list[Finding] = []

        all_funcs: dict[str, list[SymbolDef]] = {}
        for table in self.file_tables.values():
            for sym in table.symbols.values():
                if sym.kind in ("function", "async_function", "method"):
                    all_funcs.setdefault(sym.name, []).append(sym)

        for file_path, table in self.file_tables.items():
            for call in table.calls:
                if call.has_varargs or call.has_varkwargs:
                    continue

                call_name = call.name.split(".")[-1]
                candidates = all_funcs.get(call_name)
                if not candidates or len(candidates) > 1:
                    continue

                target_sym = candidates[0]
                params = target_sym.parameters
                if not params:
                    if call.args_count > 0 or call.kwargs_names:
                        target_f = Path(file_path).name
                        findings.append(
                            Finding(
                                file=file_path,
                                line=call.line,
                                severity=Severity.ERROR,
                                category=Category.BUG_RISK,
                                agent=AgentType.SEMANTIC,
                                message=(
                                    f"Call to '{call_name}()' takes 0 arguments, but "
                                    f"{call.args_count} positional and {len(call.kwargs_names)} "
                                    f"keyword arguments were given."
                                ),
                                suggestion=(
                                    f"Update call site in {target_f} to match "
                                    f"signature '{call_name}()'."
                                ),
                                rule_id="SEM003",
                            )
                        )
                    continue

                effective_params = list(params)
                is_method = target_sym.kind == "method" and effective_params
                if is_method and effective_params[0].name in ("self", "cls"):
                    if "." in call.name:
                        effective_params = effective_params[1:]

                has_varargs_param = any(p.kind == "VAR_POSITIONAL" for p in effective_params)
                has_varkwargs_param = any(p.kind == "VAR_KEYWORD" for p in effective_params)

                required_params = [
                    p
                    for p in effective_params
                    if not p.has_default and p.kind not in ("VAR_POSITIONAL", "VAR_KEYWORD")
                ]

                supplied_kw_names = set(call.kwargs_names)
                missing_required: list[str] = []

                positional_satisfied = min(call.args_count, len(required_params))
                for i, req in enumerate(required_params):
                    if i >= positional_satisfied and req.name not in supplied_kw_names:
                        missing_required.append(req.name)

                if missing_required:
                    missing_str = ", ".join(f"'{m}'" for m in missing_required)
                    findings.append(
                        Finding(
                            file=file_path,
                            line=call.line,
                            severity=Severity.ERROR,
                            category=Category.BUG_RISK,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f"Call to '{call_name}()' is missing required argument(s): "
                                f"{missing_str}."
                            ),
                            suggestion=(
                                f"Supply required parameter(s) {missing_str} or update "
                                f"the definition in {Path(target_sym.file).name}."
                            ),
                            rule_id="SEM003",
                        )
                    )
                    continue

                if not has_varargs_param:
                    pos_kinds = ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")
                    max_pos = sum(1 for p in effective_params if p.kind in pos_kinds)
                    if call.args_count > max_pos:
                        findings.append(
                            Finding(
                                file=file_path,
                                line=call.line,
                                severity=Severity.ERROR,
                                category=Category.BUG_RISK,
                                agent=AgentType.SEMANTIC,
                                message=(
                                    f"Call to '{call_name}()' passed too many positional args: "
                                    f"expected at most {max_pos}, got {call.args_count}."
                                ),
                                suggestion=(
                                    f"Remove excess positional argument(s) from '{call_name}'."
                                ),
                                rule_id="SEM003",
                            )
                        )
                        continue

                if not has_varkwargs_param and call.kwargs_names:
                    kw_kinds = ("POSITIONAL_OR_KEYWORD", "KEYWORD_ONLY")
                    valid_kw_names = {p.name for p in effective_params if p.kind in kw_kinds}
                    unexpected_kws = [kw for kw in call.kwargs_names if kw not in valid_kw_names]
                    if unexpected_kws:
                        unexpected_str = ", ".join(f"'{kw}'" for kw in unexpected_kws)
                        findings.append(
                            Finding(
                                file=file_path,
                                line=call.line,
                                severity=Severity.ERROR,
                                category=Category.BUG_RISK,
                                agent=AgentType.SEMANTIC,
                                message=(
                                    f"Call to '{call_name}()' passed unexpected keyword arg(s): "
                                    f"{unexpected_str}."
                                ),
                                suggestion=(
                                    f"Remove unexpected argument(s) {unexpected_str} or define in "
                                    f"{Path(target_sym.file).name}."
                                ),
                                rule_id="SEM003",
                            )
                        )

        return findings

    def check_unused_exports(self) -> list[Finding]:
        findings: list[Finding] = []

        all_referenced_names: set[str] = set()
        for table in self.file_tables.values():
            for call in table.calls:
                all_referenced_names.add(call.name.split(".")[-1])
            for imp in table.imports:
                all_referenced_names.add(imp.imported_name)

        for file_path, table in self.file_tables.items():
            if "test" in file_path.lower() or file_path.endswith("__init__.py"):
                continue

            for sym in table.symbols.values():
                if sym.kind not in ("function", "class"):
                    continue

                if sym.name.startswith("_") or sym.name.startswith("test_"):
                    continue

                if table.all_exports is not None and sym.name not in table.all_exports:
                    continue

                if sym.name not in all_referenced_names:
                    findings.append(
                        Finding(
                            file=file_path,
                            line=sym.line,
                            severity=Severity.INFO,
                            category=Category.CODE_QUALITY,
                            agent=AgentType.SEMANTIC,
                            message=(
                                f"Public {sym.kind} '{sym.name}' is defined but never referenced "
                                f"in the analyzed changeset."
                            ),
                            suggestion=(
                                f"If '{sym.name}' is an external public API, add tests. "
                                f"Otherwise prefix with '_' if internal."
                            ),
                            rule_id="SEM004",
                        )
                    )
        return findings
