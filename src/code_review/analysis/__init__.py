from code_review.analysis.ast_hasher import (
    compute_ast_hash,
    compute_diff_semantic_hash,
    is_semantically_identical,
    normalize_ast,
)
from code_review.analysis.dependency_graph import DependencyGraph
from code_review.analysis.multi_hunk import HunkScopeInfo, MultiHunkAnalyzer
from code_review.analysis.patterns import PatternDetector
from code_review.analysis.symbol_table import (
    FileSymbolTable,
    ImportDef,
    ParameterDef,
    SymbolCall,
    SymbolDef,
    build_file_symbol_table,
)

__all__ = [
    "DependencyGraph",
    "FileSymbolTable",
    "HunkScopeInfo",
    "ImportDef",
    "MultiHunkAnalyzer",
    "ParameterDef",
    "PatternDetector",
    "SymbolCall",
    "SymbolDef",
    "build_file_symbol_table",
    "compute_ast_hash",
    "compute_diff_semantic_hash",
    "is_semantically_identical",
    "normalize_ast",
]
