# Multi-Agent Code Review System — Project Audit & Roadmap

## 1. Project Goal

Build a system that reviews GitHub pull-request diffs using **specialist AI agents** — each focused on a different concern (security, code quality, performance, documentation) — coordinated by an **orchestrator** that merges their findings into one structured review.

The key architectural idea: instead of one monolithic reviewer, use **multiple specialized agents** that each do one job well, then combine their results. This mirrors how real engineering teams do code review — a security engineer notices different things than a performance engineer.

---

## 2. Current Implementation Status

### Milestone 1 — Project Foundation
See [Milestone 1 Documentation](milestone_1.md) for full architecture and component breakdown.

| File | Purpose |
| ------ | --------- |
| `pyproject.toml` | Build config, dependencies, tool settings |
| `.env.example` | Environment variable template |
| `.env` | Actual secrets (gitignored) |
| `.gitignore` | Git exclusion rules |
| `README.md` | Project overview |
| `src/code_review/__init__.py` | Package init, `__version__` |
| `src/code_review/config.py` | Pydantic-based settings from env vars |
| `src/code_review/logging_setup.py` | Structured logging to stderr |
| `tests/__init__.py` | Makes tests a package |
| `tests/test_config.py` | 9 tests for config defaults, env vars, validation |
| `tests/test_logging.py` | 4 tests for logging setup |

### Milestone 2 — Data Models, Diff Parsing & Agent Interface
See [Milestone 2 Documentation](milestone_2.md) for data schemas, diff parser details, and BaseAgent contract.

| File | Purpose |
| ------ | --------- |
| `src/code_review/models/enums.py` | Severity, Category, AgentType StrEnums and rank helper |
| `src/code_review/models/finding.py` | Finding Pydantic model (frozen, validated) |
| `src/code_review/models/review.py` | ReviewResult Pydantic model with computed properties |
| `src/code_review/models/__init__.py` | Public models API export |
| `src/code_review/parsers/diff_parser.py` | Unified diff parser using unidiff |
| `src/code_review/parsers/__init__.py` | Public parsers API export |
| `src/code_review/agents/base.py` | Abstract BaseAgent ABC contract |
| `src/code_review/agents/__init__.py` | Public agents API export |
| `tests/test_models.py` | 27 tests for enums, Finding, and ReviewResult |
| `tests/test_diff_parser.py` | 26 tests for diff parsing and line mapping |
| `tests/test_base_agent.py` | 8 tests for BaseAgent interface and stub |
| `tests/fixtures/sample.diff` | Single-file, multi-hunk diff fixture |
| `tests/fixtures/multi_file.diff` | Multi-file diff fixture |

### Milestone 3 — Deterministic Review Agents
See [Milestone 3 Documentation](milestone_3.md) for agent specifications, rule mappings, and test coverage.

| File | Purpose |
| ------ | --------- |
| `src/code_review/agents/ast_agent.py` | AST-based complexity, depth, length, wildcard import analysis |
| `src/code_review/agents/ruff_agent.py` | Ruff linter wrapper with JSON diagnostic parsing & diff filtering |
| `src/code_review/agents/bandit_agent.py` | Bandit security scanner wrapper with JSON parsing & diff filtering |
| `src/code_review/agents/__init__.py` | Exports BaseAgent, ASTAgent, RuffAgent, BanditAgent |
| `tests/fixtures/sample_complex.py` | Test fixture with intentional complexity/nesting/length issues |
| `tests/fixtures/sample_lint_issues.py` | Test fixture with intentional linting defects |
| `tests/fixtures/sample_security.py` | Test fixture with intentional security flaws |
| `tests/test_ast_agent.py` | 18 tests for ASTAgent metrics, rules, and diff filtering |
| `tests/test_ruff_agent.py` | 15 tests for RuffAgent execution, parsing, and filtering |
| `tests/test_bandit_agent.py` | 17 tests for BanditAgent execution, severity mapping, and filtering |
### Milestone 4 — Review Orchestrator
See [Milestone 4 Documentation](milestone_4.md) for orchestrator coordination, deduplication, and fault tolerance details.

| File | Purpose |
| ------ | --------- |
| `src/code_review/orchestrator.py` | Coordinates review agents, deduplicates findings, rank-sorts, builds ReviewResult |
| `src/code_review/__init__.py` | Exports ReviewOrchestrator, Orchestrator, deduplicate_findings, sort_findings |
| `tests/test_orchestrator.py` | 51 tests for registry, execution modes, fault tolerance, deduplication, and integration |

### Milestone 5 — LLM Integration (Ollama + Qwen 2.5 Coder)
See [Milestone 5 Documentation](milestone_5.md) for local model inference, prompt design, and anti-hallucination filtering.

| File | Purpose |
| ------ | --------- |
| `src/code_review/config.py` | LLM settings (model, provider, base URL, timeout, temperature) |
| `src/code_review/llm/client.py` | Lightweight Ollama REST client with health checks & JSON mode |
| `src/code_review/llm/prompts.py` | Review prompts, diff hunk formatter, and Finding parser |
| `src/code_review/llm/__init__.py` | Exports OllamaClient, prompts, and parsers |
| `src/code_review/agents/llm_agent.py` | LLMAgent BaseAgent implementation with fault isolation |
| `src/code_review/agents/__init__.py` | Exports LLMAgent |
| `src/code_review/orchestrator.py` | Updated default_agents and ReviewOrchestrator with include_llm option |
| `tests/fixtures/sample_logic_bugs.py` | Test fixture with intentional semantic and logic defects |
| `tests/fixtures/sample_logic.diff` | Realistic diff fixture introducing logic bugs |
| `tests/test_llm_agent.py` | 31 unit, orchestrator, and live Ollama integration tests |

### Milestone 6 — CLI Interface & Developer Tooling
See [Milestone 6 Documentation](milestone_6.md) for CLI commands, rich formatting, and CI exit codes.

| File | Purpose |
| ------ | --------- |
| `pyproject.toml` | `rich` dependency & `[project.scripts]` `code-review` entry point |
| `src/code_review/cli/git.py` | Git subprocess helpers (working tree, staged, branch) |
| `src/code_review/cli/formatter.py` | Rich table panels, severity badges, JSON, & Markdown formatters |
| `src/code_review/cli/main.py` | CLI parser, diff input resolution, quality gate exit codes |
| `src/code_review/cli/__init__.py` | CLI package init and public API re-exports |
| `src/code_review/__main__.py` | Enables running `python -m code_review` |
| `tests/fixtures/sample_issues.diff` | Deterministic diff fixture with security issues |
| `tests/test_cli.py` | 45 unit, git, format, and quality gate tests |
| `docs/milestone_6.md` | Milestone 6 architectural documentation |

### Milestone 7 — Interactive Web UI & Deployment (NEXARION)

| File | Purpose |
| ------ | --------- |
| `src/code_review/web/app.py` | FastAPI application, middleware, CORS, lifecycle |
| `src/code_review/web/routes/` | Modular API routers (reviews, conversations, pull requests, agents, auth, overview) |
| `src/code_review/db/` | SQLAlchemy models, engine, session factory, PostgreSQL migrations, default seeds |
| `src/code_review/services/github_service.py` | GitHub REST client for user repositories, PR listings, diffs, and reviews |
| `frontend/src/` | React 19 + TypeScript + Vite responsive dashboard (Overview, PRs, Reviews, Chat, Settings) |
| `tests/test_web_api.py` | Web API endpoint tests, authentication isolation, cascade deletion |

### Milestone 8 — Advanced Analysis (Cross-File & Semantic Review)
See [Milestone 8 Documentation](milestone_8.md) for cross-file dependency graph, multi-hunk analysis, and rule specifications.

| File | Purpose |
| ------ | --------- |
| `src/code_review/models/enums.py` | Added `AgentType.SEMANTIC = "semantic"` |
| `src/code_review/analysis/symbol_table.py` | AST extraction of functions, classes, imports, call sites, and exports |
| `src/code_review/analysis/dependency_graph.py` | Cross-file graph, circular imports (`SEM001`), broken imports (`SEM002`), signatures (`SEM003`), unused exports (`SEM004`) |
| `src/code_review/analysis/multi_hunk.py` | Multi-hunk resource leaks (`SEM005`), variable collisions (`SEM006`), diff context summary |
| `src/code_review/analysis/patterns.py` | Code clones (`SEM007`), swallowed errors (`SEM008`), repeated magic constants (`SEM009`) |
| `src/code_review/analysis/__init__.py` | Public analysis engine API exports |
| `src/code_review/agents/semantic_agent.py` | `SemanticAgent` (`CrossFileAgent`) implementing `BaseAgent` contract |
| `src/code_review/orchestrator.py` | Integrated `include_semantic` in `default_agents()` and `ReviewOrchestrator` |
| `src/code_review/cli/main.py` | Added `--semantic` flag and `semantic` / `cross_file` agent mapping |
| `src/code_review/llm/prompts.py` | Enriched LLM prompt formatting with multi-hunk context summaries |
| `src/code_review/db/init_db.py` | Registered `semantic` agent in PostgreSQL default seed catalog |
| `tests/fixtures/sample_cross_file_broken.diff` | Multi-file diff fixture with broken imports, signature mismatches, cycles |
| `tests/fixtures/sample_multi_hunk_leak.diff` | Multi-hunk diff fixture with resource leaks and variable collisions |
| `tests/test_analysis.py` | 18 unit tests for symbol tables, dependency graphs, multi-hunk, and pattern algorithms |
| `tests/test_semantic_agent.py` | 11 unit and integration tests for SemanticAgent, orchestrator, and CLI |
| `docs/milestone_8.md` | Milestone 8 architectural documentation and rules catalog |

### Milestone 9 — Caching & Performance
See [Milestone 9 Documentation](milestone_9.md) for caching architectures, AST semantic hashing, and async orchestration.

| File | Purpose |
| ------ | --------- |
| `src/code_review/cache/base.py` | `BaseCache` abstract interface and `CacheEntry` dataclass with TTL support |
| `src/code_review/cache/keys.py` | `compute_diff_hash`, `normalize_diff_text`, and `compute_cache_key` |
| `src/code_review/cache/memory_cache.py` | Thread-safe `MemoryCache` with LRU eviction, access ordering, and TTL |
| `src/code_review/cache/disk_cache.py` | Persistent `DiskCache` with atomic temporary writes and directory pruning |
| `src/code_review/cache/__init__.py` | Public cache subsystem exports |
| `src/code_review/analysis/ast_hasher.py` | AST normalizer, `compute_ast_hash`, and `compute_diff_semantic_hash` |
| `src/code_review/models/review.py` | Added `cached: bool = False` metadata field to `ReviewResult` |
| `src/code_review/agents/base.py` | Added `review_async()` non-blocking interface to `BaseAgent` |
| `src/code_review/orchestrator.py` | Integrated cache lookup/storage, `review_async`, `_run_async`, and semaphores |
| `src/code_review/config.py` | Added caching settings (`cache_enabled`, `cache_backend`, `cache_dir`, `cache_ttl_seconds`) |
| `src/code_review/cli/main.py` | Added `--no-cache`, `--cache-dir`, `--clear-cache`, `--semantic-cache` CLI flags |
| `src/code_review/cli/formatter.py` | Added `[CACHED]` badge to terminal review summary panel |
| `tests/test_cache.py` | 17 unit tests for diff hashing, MemoryCache, and DiskCache |
| `tests/test_ast_hasher.py` | 6 unit tests for AST normalization, whitespace/comment invariance, diff hashing |
| `tests/test_async_orchestrator.py` | 9 integration tests for async dispatch, parallel speedup, fault tolerance, and cache hits |
| `docs/milestone_9.md` | Milestone 9 architectural documentation |

**Test results:** 345/345 passing (100% pass rate) [PASS]
**Linter:** Ruff clean [PASS]

---

## 3. Milestone Roadmap

### Milestone Map Overview

```
M1  Foundation                   ████████████ DONE
M2  Models & Parsing             ████████████ DONE
M3  Deterministic Agents         ████████████ DONE
M4  Orchestrator                 ████████████ DONE
M5  LLM Integration              ████████████ DONE
M6  CLI Interface                ████████████ DONE
M7  Interactive Web UI & Deploy  ████████████ DONE (NEXARION)
M8  Advanced Analysis            ████████████ DONE
M9  Caching & Perf               ████████████ DONE
M10 Testing, Docker & CI/CD      ████████████ DONE
M11 GitHub Integration           ████████████ DONE
```

---

### Milestone 3 — Deterministic Review Agents
See [Milestone 3 Specification](milestone_3.md) for design, agent specifications, and test plan.

**What it accomplishes:**
- Builds three concrete agents that analyze code **without any AI/LLM**:
  - **AST Agent** — uses Python's built-in `ast` module to detect complexity, deep nesting, and structural issues.
  - **Ruff Agent** — wraps the Ruff linter and parses its JSON output.
  - **Bandit Agent** — wraps the Bandit security scanner and parses its JSON output.
- Each agent implements the `BaseAgent` interface from M2.

**Why it's necessary:**
Deterministic agents give you a reliable baseline. They always produce the same output for the same input. When you add LLM agents later (M5), you can compare: did the AI catch what the deterministic tools missed? This is how you validate AI quality.

**Files to create:**
```
src/code_review/agents/
├── ast_agent.py
├── ruff_agent.py
└── bandit_agent.py
tests/
├── test_ast_agent.py
├── test_ruff_agent.py
├── test_bandit_agent.py
└── fixtures/
    ├── sample_complex.py
    ├── sample_lint_issues.py# Code with linting problems for Ruff agent
    └── sample_security.py
```

**New dependencies:** `bandit`

**Prerequisites & Key Concepts:**
1. Python's `ast` module (`ast.parse`, `ast.NodeVisitor`, `ast.walk`)
2. Cyclomatic complexity (counting branches)
3. `subprocess.run()` (calling external tools from Python securely)
4. Ruff's JSON output format (`ruff check --output-format json`)
5. Bandit's JSON output format (`bandit -f json`)
6. Filtering results to only changed lines (connecting agents to diff parser)

---

### Milestone 4 — Review Orchestrator
See [Milestone 4 Specification](milestone_4.md) for architecture, design decisions, and verification details.

**What it accomplishes:**
- Builds the **Orchestrator** that coordinates all specialist agents:
  - Runs agents sequentially or concurrently via `ThreadPoolExecutor`.
  - Aggregates findings with fault-tolerant error boundaries.
  - Deduplicates overlapping findings across tools by `(file, line, rule_id)` / message, preferring higher severity and actionable suggestions.
  - Sorts findings by severity rank (`CRITICAL` > `ERROR` > `WARNING` > `INFO`) with deterministic file/line tie-breaking.
  - Produces a final structured and validated `ReviewResult` with review duration metadata.

**Files created:**
```
src/code_review/
├── orchestrator.py
tests/
├── test_orchestrator.py
docs/
├── milestone_4.md
```

---

### Milestone 5 — LLM Integration
See [Milestone 5 Specification](milestone_5.md) for local model inference, prompt design, and anti-hallucination filtering.

**What it accomplishes:**
- Adds an **LLM-powered agent** that uses a local model (Ollama + Qwen 2.5 Coder) to review code for subtle issues that deterministic tools miss (unclear naming, missing edge cases, logic errors).
- Integrates `OllamaClient` using Python standard library `urllib` (zero external dependencies).
- Enforces strict anti-hallucination filtering to ensure findings are only placed on lines added in the pull request diff.
- Employs Ollama's constrained JSON mode (`format: "json"`) for guaranteed syntax compliance.

**Files created:**
```
src/code_review/llm/
├── client.py
├── prompts.py
└── __init__.py
src/code_review/agents/
└── llm_agent.py
tests/
├── fixtures/
│   ├── sample_logic_bugs.py
│   └── sample_logic.diff
└── test_llm_agent.py
docs/
└── milestone_5.md
```

---

### Milestones 6–10 — CLI, Web UI, Advanced Analysis, Caching, CI

| Milestone | Focus | Key Topics |
|-----------|-------|------------|
| **M6** | **CLI Interface & Developer Tooling** | `code-review` entry point, stdin streaming (`git diff \| code-review`), Git automation (`--staged`, `--branch`), colored rich badges, CI exit codes (`--fail-on`) |
| **M7** | **Interactive Web UI & Deployment** | FastAPI review API, **Interactive Web Dashboard** (designed per user's prompt), dual-provider LLM (local Ollama + free cloud LLM fallback for $0 live deployment), export options |
| **M8** | **Advanced Analysis** | Cross-file analysis, pattern detection, multi-hunk semantic context |
| **M9** | **Caching & Performance** | Review result caching, AST hash checking, `asyncio` concurrency |
| **M10** | **Testing, Docker & CI/CD** | Production `Dockerfile`, GitHub Actions CI test/coverage gates, automated cloud deploy |

---

### Milestone 6 — CLI Interface & Developer Tooling
See [Milestone 6 Specification](milestone_6.md) for terminal design, git automation, and test coverage.

**What it accomplishes:**
- Creates a developer-friendly terminal application with the `code-review` command installed via `pyproject.toml` entry points (`[project.scripts]`).
- Supports reading diffs from file arguments, piping from standard input (`git diff | code-review`), or inspecting active git branches/staged changes directly.
- Formats findings with clean colored terminal tables and severity badges (`rich` console).
- Returns configurable process exit codes (`--fail-on error`) to integrate into pre-commit hooks and CI scripts.

**Files created:**
```
src/code_review/
├── __main__.py
└── cli/
    ├── __init__.py
    ├── git.py
    ├── formatter.py
    └── main.py
tests/
├── fixtures/
│   └── sample_issues.diff
└── test_cli.py
docs/
└── milestone_6.md
```

---

### Milestone 7 — Interactive Web UI & Cloud Deployment (NEXARION)

**What it accomplishes:**
- Builds a lightweight **FastAPI** backend exposing `POST /api/reviews`, conversations, pull requests, and agent management endpoints.
- Implements an **Interactive Web Dashboard** (React 19 + TypeScript + Vite) with responsive views (Overview, Pull Requests, Reviews, Chat, and Settings).
- Enables public deployment for job interviews and portfolio showcase (free cloud hosting on Render / Railway / Hugging Face Spaces).
- Adds dual-mode LLM provider support (local Ollama for offline dev, NVIDIA cloud API fallback for free 24/7 public demo hosting).

---

### Milestone 8 — Advanced Analysis (Cross-File & Semantic Review)
See [Milestone 8 Specification](milestone_8.md) for full architecture, AST symbol extraction, dependency graph mechanics, and rules catalog.

**What it accomplishes:**
- Implements cross-file symbol tracking, detecting circular module dependencies (`SEM001`), broken imports / missing symbols (`SEM002`), call signature mismatches (`SEM003`), and dead public exports (`SEM004`).
- Implements multi-hunk semantic analysis, detecting cross-hunk unclosed resource leaks (`SEM005`) and cross-hunk variable collisions / scope shadowing (`SEM006`).
- Generates structured multi-hunk diff context summaries and injects them into LLM review prompts for richer reasoning.
- Implements code pattern detection for AST-normalized duplicate code clones (`SEM007`), silently swallowed exceptions (`SEM008`), and repeated magic constants (`SEM009`).
- Exposes `SemanticAgent` (`CrossFileAgent`) via `AgentType.SEMANTIC`, integrates into `ReviewOrchestrator(include_semantic=True)`, CLI (`--semantic`), PostgreSQL seed catalog, and Web API.

**Files created:**
```
src/code_review/analysis/
├── __init__.py
├── symbol_table.py
├── dependency_graph.py
├── multi_hunk.py
└── patterns.py
src/code_review/agents/
└── semantic_agent.py
tests/
├── fixtures/
│   ├── sample_cross_file_broken.diff
│   └── sample_multi_hunk_leak.diff
├── test_analysis.py
└── test_semantic_agent.py
docs/
└── milestone_8.md
```

---

### Milestone 9 — Caching & Performance
See [Milestone 9 Specification](milestone_9.md) for caching architectures, AST semantic hashing, and async orchestration.

**What it accomplishes:**
- Implements two-tier review result caching: thread-safe `MemoryCache` with LRU eviction and atomic `DiskCache` for persistence.
- Implements deterministic unified diff fingerprinting (`compute_diff_hash`) and cache key generation (`compute_cache_key`).
- Introduces **AST Semantic Hashing** (`compute_ast_hash`, `compute_diff_semantic_hash`, `is_semantically_identical`) that normalizes syntax trees to avoid re-reviewing pure comment, whitespace, or docstring modifications.
- Adds native asynchronous agent review execution (`review_async`, `review_diff_async`, `review_files_async`, `_run_async`) with `asyncio.to_thread` worker threads and `asyncio.Semaphore` concurrency limiting.
- Adds CLI caching flags (`--no-cache`, `--cache-dir`, `--clear-cache`, `--semantic-cache`) and terminal `[CACHED]` indicators.

**Files created:**
```
src/code_review/cache/
├── __init__.py
├── base.py
├── keys.py
├── memory_cache.py
└── disk_cache.py
src/code_review/analysis/
└── ast_hasher.py
tests/
├── test_cache.py
├── test_ast_hasher.py
└── test_async_orchestrator.py
docs/
└── milestone_9.md
```

---

### Milestone 10 — Testing, Docker & CI/CD
See [Milestone 10 Specification](milestone_10.md) for containerization architecture, GitHub Actions pipeline, and deployment instructions.

**What it accomplishes:**
- Creates production multi-stage `Dockerfile` (Node 20 Vite builder + Python 3.12 slim runtime with non-root security) and `docker-compose.yml` orchestrating PostgreSQL 16, Ollama, and NEXARION.
- Creates standalone `frontend/Dockerfile` and production `frontend/nginx.conf` with reverse proxy and gzip compression.
- Sets up `.github/workflows/ci.yml` running lint checks (`ruff`), security checks (`bandit`), Python 3.11/3.12 pytest matrix with PostgreSQL container service, frontend tests, and Docker build verification.
- Configures comprehensive coverage enforcement (`>= 80%`) and adds `test_health_and_deployment.py` (353 total passing tests).
- Achieves 100% clean Ruff linting and format compliance across the codebase.

**Files created / updated:**
```
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── pyproject.toml
frontend/
├── Dockerfile
└── nginx.conf
.github/workflows/
└── ci.yml
tests/
└── test_health_and_deployment.py
docs/
└── milestone_10.md
```

---

### Milestone 11 — GitHub Integration
See [Milestone 11 Specification](milestone_11.md) for webhook architecture, HMAC verification, PR inline comment mapping, and commit status checks.

**What it accomplishes:**
- Connects the system to GitHub: listens for PR webhooks, validates HMAC-SHA256 signatures, deduplicates deliveries, returns fast 202 responses (< 100ms).
- Dispatches background multi-agent reviews (AST, Ruff, Bandit, Semantic, LLM) without blocking the webhook connection.
- Posts structured PR reviews with summary metrics, agent breakdowns, and inline code suggestions (````suggestion````) mapped to valid diff lines.
- Automatically handles HTTP 422 diff line discrepancies by compiling unmapped findings into the review body so zero findings are lost.
- Sets GitHub Commit Status checks (`pending`, `success`, `failure`).
- Adds manual PR review publishing via `POST /api/github/repos/{owner}/{repo}/pulls/{number}/post-review` and frontend `githubApi.postReview`.

**Files created / updated:**
```
src/code_review/github/
├── service.py
src/code_review/web/routes/
├── github_routes.py
src/code_review/
├── config.py
frontend/src/services/
├── api.ts
tests/
├── test_github_integration.py
docs/
└── milestone_11.md
```
