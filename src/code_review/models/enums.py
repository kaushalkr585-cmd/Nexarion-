from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


def severity_rank(severity: Severity) -> int:
    return SEVERITY_RANK[severity]


class Category(StrEnum):
    SECURITY = "security"
    CODE_QUALITY = "code_quality"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    BUG_RISK = "bug_risk"
    BEST_PRACTICE = "best_practice"


class AgentType(StrEnum):
    AST = "ast"
    RUFF = "ruff"
    BANDIT = "bandit"
    LLM = "llm"
    SEMANTIC = "semantic"
