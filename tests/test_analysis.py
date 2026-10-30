from __future__ import annotations

from code_review.analysis.dependency_graph import DependencyGraph
from code_review.analysis.multi_hunk import MultiHunkAnalyzer
from code_review.analysis.patterns import PatternDetector
from code_review.analysis.symbol_table import (
    build_file_symbol_table,
)
from code_review.models.enums import AgentType, Category, Severity
from code_review.parsers.diff_parser import parse_diff


class TestSymbolTableExtraction:
    def test_extract_function_signature_and_defaults(self) -> None:
        source = """
def calculate(a: int, b: int = 10, *args: int, factor: float = 1.5, **kwargs: str) -> float:
    \"\"\"Docstring explanation.\"\"\"
    return float(a + b)
"""
        table = build_file_symbol_table(source, "src/math_ops.py")
        assert "calculate" in table.symbols
        sym = table.symbols["calculate"]
        assert sym.name == "calculate"
        assert sym.kind == "function"
        assert sym.docstring == "Docstring explanation."
        assert sym.return_annotation == "float"

        params = sym.parameters
        assert len(params) == 5

        assert params[0].name == "a"
        assert not params[0].has_default
        assert params[0].annotation == "int"

        assert params[1].name == "b"
        assert params[1].has_default
        assert params[1].default_repr == "10"

        assert params[2].name == "args"
        assert params[2].kind == "VAR_POSITIONAL"

        assert params[3].name == "factor"
        assert params[3].kind == "KEYWORD_ONLY"
        assert params[3].has_default
        assert params[3].default_repr == "1.5"

        assert params[4].name == "kwargs"
        assert params[4].kind == "VAR_KEYWORD"

    def test_extract_classes_and_methods(self) -> None:
        source = """
class UserService:
    \"\"\"Manages user accounts.\"\"\"
    def __init__(self, db_client):
        self.db = db_client

    def get_user(self, user_id: str) -> dict:
        return {"id": user_id}
"""
        table = build_file_symbol_table(source, "src/service.py")
        assert "UserService" in table.symbols
        assert table.symbols["UserService"].kind == "class"

        assert "UserService.__init__" in table.symbols
        init_sym = table.symbols["UserService.__init__"]
        assert init_sym.kind == "method"
        assert init_sym.parent == "UserService"

        assert "UserService.get_user" in table.symbols
        get_sym = table.symbols["UserService.get_user"]
        assert get_sym.kind == "method"
        assert get_sym.parent == "UserService"

    def test_extract_imports_and_calls(self) -> None:
        source = """
import os
from math import sqrt as square_root
from .utils import helper

def run():
    x = square_root(16)
    helper(x, flag=True)
"""
        table = build_file_symbol_table(source, "src/main.py")

        mod_names = [imp.imported_name for imp in table.imports]
        assert "os" in mod_names
        assert "sqrt" in mod_names
        assert "helper" in mod_names

        call_names = [c.name for c in table.calls]
        assert "square_root" in call_names
        assert "helper" in call_names

        helper_call = next(c for c in table.calls if c.name == "helper")
        assert helper_call.args_count == 1
        assert "flag" in helper_call.kwargs_names

    def test_extract_all_exports(self) -> None:
        source = """
__all__ = ["PublicClass", "public_func"]

class PublicClass:
    pass

class _PrivateClass:
    pass

def public_func():
    pass
"""
        table = build_file_symbol_table(source, "src/exports.py")
        assert table.all_exports == ["PublicClass", "public_func"]
        assert table.is_publicly_exported("PublicClass") is True
        assert table.is_publicly_exported("public_func") is True
        assert table.is_publicly_exported("_PrivateClass") is False

    def test_syntax_error_returns_empty_table(self) -> None:
        table = build_file_symbol_table("def broken_syntax(x:", "src/bad.py")
        assert len(table.symbols) == 0
        assert len(table.imports) == 0


class TestDependencyGraph:
    def test_circular_dependency_detected(self) -> None:
        source_a = "from mod_b import func_b\ndef func_a(): pass\n"
        source_b = "from mod_a import func_a\ndef func_b(): pass\n"

        table_a = build_file_symbol_table(source_a, "src/mod_a.py")
        table_b = build_file_symbol_table(source_b, "src/mod_b.py")

        dep_graph = DependencyGraph({"src/mod_a.py": table_a, "src/mod_b.py": table_b})
        findings = dep_graph.check_circular_dependencies()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM001"
        assert f.severity == Severity.WARNING
        assert f.category == Category.CODE_QUALITY
        assert f.agent == AgentType.SEMANTIC
        assert "Circular dependency" in f.message

    def test_broken_cross_file_import_detected(self) -> None:
        source_a = "def existing_function(): pass\n"
        source_b = "from src.mod_a import deleted_function\n"

        table_a = build_file_symbol_table(source_a, "src/mod_a.py")
        table_b = build_file_symbol_table(source_b, "src/mod_b.py")

        dep_graph = DependencyGraph({"src/mod_a.py": table_a, "src/mod_b.py": table_b})
        findings = dep_graph.check_broken_imports()

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "SEM002"
        assert f.severity == Severity.ERROR
        assert f.category == Category.BUG_RISK
        assert "deleted_function" in f.message

    def test_call_signature_missing_required_argument(self) -> None:
        source_a = "def send_email(recipient: str, subject: str, body: str) -> bool: pass\n"
        source_b = (
            "from src.mailer import send_email\ndef notify():\n    send_email('user@test.com')\n"
        )

        table_a = build_file_symbol_table(source_a, "src/mailer.py")
        table_b = build_file_symbol_table(source_b, "src/notifier.py")

        dep_graph = DependencyGraph({"src/mailer.py": table_a, "src/notifier.py": table_b})
        findings = dep_graph.check_call_signatures()

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "SEM003"
        assert f.severity == Severity.ERROR
        assert "missing required argument" in f.message

    def test_call_signature_excess_positional_arguments(self) -> None:
        source_a = "def add(x: int, y: int) -> int: pass\n"
        source_b = "from src.math_mod import add\ndef compute():\n    return add(1, 2, 3, 4)\n"

        table_a = build_file_symbol_table(source_a, "src/math_mod.py")
        table_b = build_file_symbol_table(source_b, "src/consumer.py")

        dep_graph = DependencyGraph({"src/math_mod.py": table_a, "src/consumer.py": table_b})
        findings = dep_graph.check_call_signatures()

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "SEM003"
        assert "too many positional" in f.message

    def test_call_signature_unexpected_keyword_argument(self) -> None:
        source_a = "def create_user(name: str, email: str) -> None: pass\n"
        source_b = (
            "from src.users import create_user\n"
            "def setup():\n"
            "    create_user('Alice', 'a@a.com', role='admin')\n"
        )

        table_a = build_file_symbol_table(source_a, "src/users.py")
        table_b = build_file_symbol_table(source_b, "src/admin.py")

        dep_graph = DependencyGraph({"src/users.py": table_a, "src/admin.py": table_b})
        findings = dep_graph.check_call_signatures()

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "SEM003"
        assert "unexpected keyword" in f.message
        assert "'role'" in f.message

    def test_unused_export_detected(self) -> None:
        source_a = "def orphaned_utility(): pass\n"
        table_a = build_file_symbol_table(source_a, "src/unused.py")

        dep_graph = DependencyGraph({"src/unused.py": table_a})
        findings = dep_graph.check_unused_exports()

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "SEM004"
        assert f.severity == Severity.INFO
        assert "orphaned_utility" in f.message


class TestMultiHunkAnalyzer:
    def test_cross_hunk_resource_leak_detected(self) -> None:
        diff_text = """--- a/src/worker.py
+++ b/src/worker.py
@@ -5,4 +5,6 @@ def run(path: str):
     print("starting")
+    f = open(path, "r")
+    data = f.read()
@@ -20,4 +22,6 @@ def check_status(code: int):
     print("checking")
+    if code < 0:
+        return None
"""
        diff_files = parse_diff(diff_text)
        assert len(diff_files) == 1
        df = diff_files[0]

        analyzer = MultiHunkAnalyzer(df)
        findings = analyzer.check_cross_hunk_resource_leaks()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM005"
        assert f.severity == Severity.ERROR
        assert "Resource 'f' acquired in earlier hunk" in f.message

    def test_cross_hunk_variable_collision_detected(self) -> None:
        diff_text = """--- a/src/calc.py
+++ b/src/calc.py
@@ -10,4 +10,5 @@ def step1():
+    threshold = 100
     return threshold
@@ -30,4 +31,5 @@ def step2():
+    threshold = "unrelated_string"
     return threshold
"""
        diff_files = parse_diff(diff_text)
        analyzer = MultiHunkAnalyzer(diff_files[0])
        findings = analyzer.check_cross_hunk_variable_collisions()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM006"
        assert f.severity == Severity.WARNING
        assert "shadows previous assignment" in f.message

    def test_multi_hunk_context_summary_generation(self) -> None:
        diff_text = """--- a/src/calc.py
+++ b/src/calc.py
@@ -10,2 +10,4 @@
+    a = 1
+    b = 2
@@ -30,2 +32,4 @@
+    c = 3
+    d = 4
"""
        diff_files = parse_diff(diff_text)
        analyzer = MultiHunkAnalyzer(diff_files[0])
        summary = analyzer.generate_context_summary()

        assert "Multi-Hunk Context" in summary
        assert "Hunk 1" in summary
        assert "Hunk 2" in summary


class TestPatternDetector:
    def test_detect_code_clones_across_files(self) -> None:
        diff_text = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,7 @@
+    if not user:
+        logger.error("User not found")
+        metrics.increment("auth_failure")
+        return False

diff --git a/src/billing.py b/src/billing.py
--- a/src/billing.py
+++ b/src/billing.py
@@ -20,3 +20,7 @@
+    if not user:
+        logger.error("User not found")
+        metrics.increment("auth_failure")
+        return False
"""
        diff_files = parse_diff(diff_text)
        detector = PatternDetector(diff_files, min_clone_lines=4)
        findings = detector.detect_code_clones()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM007"
        assert f.severity == Severity.WARNING
        assert "Duplicate code block" in f.message

    def test_detect_inconsistent_error_handling(self) -> None:
        diff_text = """--- a/src/parser.py
+++ b/src/parser.py
@@ -10,3 +10,5 @@
+    except:
+        print("failed")
"""
        diff_files = parse_diff(diff_text)
        detector = PatternDetector(diff_files)
        findings = detector.detect_inconsistent_error_handling()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM008"
        assert f.severity == Severity.WARNING
        assert "Bare 'except:' clause" in f.message

    def test_detect_swallowed_exception(self) -> None:
        diff_text = """--- a/src/client.py
+++ b/src/client.py
@@ -15,3 +15,5 @@
+    except Exception:
+        pass
"""
        diff_files = parse_diff(diff_text)
        detector = PatternDetector(diff_files)
        findings = detector.detect_inconsistent_error_handling()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM008"
        assert "Silently swallowed exception" in f.message

    def test_detect_repeated_magic_constants(self) -> None:
        diff_text = """diff --git a/src/service_a.py b/src/service_a.py
--- a/src/service_a.py
+++ b/src/service_a.py
@@ -1,3 +1,4 @@
+API_URL = "https://api.internal.service/v1/auth"

diff --git a/src/service_b.py b/src/service_b.py
--- a/src/service_b.py
+++ b/src/service_b.py
@@ -1,3 +1,4 @@
+ENDPOINT = "https://api.internal.service/v1/auth"
"""
        diff_files = parse_diff(diff_text)
        detector = PatternDetector(diff_files)
        findings = detector.detect_repeated_magic_constants()

        assert len(findings) >= 1
        f = findings[0]
        assert f.rule_id == "SEM009"
        assert f.severity == Severity.INFO
        assert "Repeated magic constant" in f.message
