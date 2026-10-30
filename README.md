# Multi-Agent AI Code Review System

A system that reviews GitHub pull-request changes using specialist AI agents —
each focused on security, code quality, performance, or documentation —
coordinated by an orchestrator that produces one structured review.

## Current Status: Milestone 5 — LLM Integration (Ollama + Qwen 2.5 Coder)

- [Milestone 1 — Project Foundation](docs/milestone_1.md) (complete, 13 tests)
- [Milestone 2 — Data Models, Diff Parsing & Agent Interface](docs/milestone_2.md) (complete, 61 new tests)
- [Milestone 3 — Deterministic Review Agents](docs/milestone_3.md) (complete, 50 new tests)
- [Milestone 4 — Review Orchestrator](docs/milestone_4.md) (complete, 51 new tests)
- [Milestone 5 — LLM Integration](docs/milestone_5.md) (complete, 31 new tests, 208 total passing, 94% coverage)
- [Milestone 6 — CLI Interface & Developer Tooling](docs/ROADMAP.md) (next)
- [Milestone 7 — Interactive Web Dashboard & Cloud Deployment](docs/ROADMAP.md)

### Milestone Documentation

Detailed architecture, design decisions, and file breakdowns are organized milestone-by-milestone:
- [docs/milestone_1.md](docs/milestone_1.md) — Foundation (settings, structured logging, build config, pytest/ruff)
- [docs/milestone_2.md](docs/milestone_2.md) — Data models, diff parser, BaseAgent ABC, test fixtures
- [docs/milestone_3.md](docs/milestone_3.md) — Deterministic review agents (AST, Ruff, Bandit)
- [docs/milestone_4.md](docs/milestone_4.md) — Review orchestrator (aggregation, deduplication, severity sorting)
- [docs/milestone_5.md](docs/milestone_5.md) — LLM integration (Ollama client, Qwen 2.5 Coder, anti-hallucination diff filtering)
- [docs/ROADMAP.md](docs/ROADMAP.md) — Master project roadmap and all 11 milestones

## Quick Start (Windows PowerShell)

```powershell

cd "E:\Projects\Multi Agent Code Review System"

python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"

Copy-Item .env.example .env

pytest

ruff check src/ tests/
```

## Project Structure

```
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── docs/
│   ├── ROADMAP.md
│   ├── milestone_1.md
│   ├── milestone_2.md
│   └── milestone_3.md
├── src/
│   └── code_review/
│       ├── __init__.py
│       ├── config.py
│       ├── logging_setup.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── enums.py
│       │   ├── finding.py
│       │   └── review.py
│       ├── parsers/
│       │   ├── __init__.py
│       │   └── diff_parser.py
│       └── agents/
│           ├── __init__.py
│           └── base.py
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_logging.py
    ├── test_models.py
    ├── test_diff_parser.py
    ├── test_base_agent.py
    └── fixtures/
        ├── sample.diff
        └── multi_file.diff
```

## Dependencies

| Package | Purpose | Cost |
|---------|---------|------|
| python-dotenv | Load .env files | Free |
| pydantic | Data validation | Free |
| pydantic-settings | Config from environment | Free |
| unidiff | Parse unified diffs | Free |
| pytest | Test runner | Free |
| pytest-cov | Test coverage | Free |
| ruff | Linter / formatter | Free |

## Limitations and Future Work

- **No concrete agents yet** — Milestone 3 adds AST, Ruff, and Bandit agents.
- **No LLM integration** — coming in Milestone 5 after a deterministic baseline.
- **No GitHub integration** — coming in Milestone 11.
- **Single-machine only** — no distributed architecture planned for the MVP.

See [roadmap](docs/ROADMAP.md) for the full plan.
