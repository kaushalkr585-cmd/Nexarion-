# Milestone 6 — CLI Interface & Developer Tooling

**Status:**  Complete
**Tests:** 45 new tests (253 total passing, 95% coverage)
**Linter:** Ruff clean

---

## 1. Overview & Objective

Milestone 6 builds a comprehensive developer-facing command-line interface (`code-review`) and terminal workflow tool for the multi-agent code review system.

While the core review engine (AST, Ruff, Bandit, LLM, and Orchestrator) provides the underlying analytical power, developers and automated CI pipelines interact with the system through the terminal and shell scripts. Milestone 6 delivers:

1. **Executable Console Entry Point**: Installs `code-review` directly into the environment via `pyproject.toml` script entry points (`[project.scripts]`), alongside `python -m code_review` module execution.
2. **Flexible Diff Sources**:
   - Inspect uncommitted working tree changes directly (`code-review`).
   - Inspect staged changes before committing (`code-review --staged` or `--cached`).
   - Compare feature branches against main (`code-review --branch main`).
   - Stream diffs from standard input (`git diff | code-review` or `code-review -`).
   - Inspect specific `.diff` or `.patch` files (`code-review path/to/file.diff`).
3. **Rich Terminal Visuals**: Uses `rich` to output formatted summary panels, colorized severity badges (`CRITICAL`, `ERROR`, `WARNING`, `INFO`), agent tags (`AST`, `RUFF`, `BANDIT`, `LLM`), code locations with line numbers, and actionable suggestions.
4. **Multiple Output Formats**: Supports human-centric `table` formatting, machine-readable `json` for downstream tooling, and GitHub-flavored `markdown` for PR descriptions or comments.
5. **CI/CD Quality Gates & Exit Codes**: Implements configurable exit thresholds (`--fail-on <severity>`). If any finding reaches or exceeds the threshold (e.g. `--fail-on error`), `code-review` exits with returncode 1, allowing seamless integration into pre-commit hooks and CI/CD pipelines.

---

## 2. Components & Files Created / Updated

| File | Type | Purpose |
|------|------|---------|
| [`pyproject.toml`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/pyproject.toml) | Build Configuration | Added `rich>=13.0.0` dependency and defined `[project.scripts]` `code-review = "code_review.cli.main:main"`. |
| [`src/code_review/cli/git.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/src/code_review/cli/git.py) | Subprocess Helpers | Implements `is_git_available()`, `is_git_repo()`, and `get_git_diff()` supporting staged, branch, and working tree diff extraction. |
| [`src/code_review/cli/formatter.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/src/code_review/cli/formatter.py) | Visual Formatter | Provides `render_table()` (rich panels and tables with severity badges), `render_json()`, and `render_markdown()`. |
| [`src/code_review/cli/main.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/src/code_review/cli/main.py) | CLI Entry Point | CLI argument parser (`argparse`), diff source resolution, agent filtering, execution orchestration, and exit code handling. |
| [`src/code_review/cli/__init__.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/src/code_review/cli/__init__.py) | Package Init | Re-exports CLI public functions and exceptions. |
| [`src/code_review/__main__.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/src/code_review/__main__.py) | Module Entry Point | Enables running `python -m code_review`. |
| [`tests/fixtures/sample_issues.diff`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/tests/fixtures/sample_issues.diff) | Test Fixture | Deterministic diff fixture with intentional security defects for fast CLI tests. |
| [`tests/test_cli.py`](file:///e:/Projects/Multi%20Agent%20Code%20Review%20System/tests/test_cli.py) | Test Suite | 45 unit and integration tests covering parser flags, diff resolution, git helpers, formatters, and exit codes. |

---

## 3. Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Inputs
        F[File Argument: patch.diff]
        P[Piped Stdin: git diff | ...]
        G[Git Flags: --staged / --branch]
        W[Working Tree: git diff]
    end

    Inputs --> RESOLVE[cli.main.resolve_diff_input]
    RESOLVE --> RAW[Raw Diff String]
    RAW --> ORCH[ReviewOrchestrator.review_diff]

    subgraph Agents Dispatch
        ORCH --> AST[ASTAgent]
        ORCH --> RUFF[RuffAgent]
        ORCH --> BANDIT[BanditAgent]
        ORCH -.->|--llm| LLM[LLMAgent]
    end

    ORCH --> RES[ReviewResult]

    subgraph Output Formatting
        RES -->|--format table| TBL[formatter.render_table: Rich Panels & Badges]
        RES -->|--format json| JSN[formatter.render_json: Valid JSON Document]
        RES -->|--format markdown| MD[formatter.render_markdown: GitHub Table]
    end

    RES --> GATE{--fail-on threshold?}
    GATE -->|Violation Found| EXIT1[Exit Code 1: Quality Gate Failed]
    GATE -->|Within Threshold| EXIT0[Exit Code 0: Quality Gate Passed]
```

### Key Design Decisions

- **Stream-Aware UTF-8 Windows Console Support**: Windows legacy consoles use `cp1252` by default which fails on non-ASCII characters or Unicode symbols. `main()` automatically reconfigures `sys.stdout` and `sys.stderr` to `utf-8` with fallback character replacement.
- **Unwrapped Clean Output for JSON/Markdown**: When `--format json` or `--format markdown` is selected, output is written directly to the output stream rather than through `rich.Console.print()`. This prevents terminal word-wrapping from breaking JSON syntax or markdown URLs.
- **Precedence-Based Input Resolution**:
  1. Explicit file path or `-` (stdin)
  2. Git options (`--staged`, `--branch`)
  3. Piped stdin (detected via `not sys.stdin.isatty()`)
  4. Git working tree repository changes
- **Composable CI/CD Exit Codes**:
  - `0`: Success (no findings or none meeting `--fail-on`).
  - `1`: Quality gate failure (findings meeting or exceeding `--fail-on`).
  - `2`: Bad arguments, file not found, or git failure.

---

## 4. CLI Command Reference & Examples

### Basic Usage
```powershell

code-review

code-review --staged

code-review --branch main

git diff HEAD~1 | code-review

code-review tests/fixtures/sample_issues.diff
```

### CI/CD Quality Gate
```powershell

code-review --staged --fail-on error

code-review --format json -o review-report.json --fail-on error
```

### Agent Selection & LLM Activation
```powershell

code-review --agents bandit

code-review --llm
```

---

## 5. Verification Commands

```powershell

.venv\Scripts\python.exe -m pytest

.venv\Scripts\python.exe -m pytest --cov=src/code_review

.venv\Scripts\python.exe -m ruff check .

.venv\Scripts\code-review.exe --version
.venv\Scripts\code-review.exe tests/fixtures/sample_issues.diff
```
