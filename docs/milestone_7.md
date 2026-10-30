# Milestone 7 — NEXARION: Interactive Web UI & Dual-Provider Deployment

## 1. Overview & Objective

Milestone 7 transforms the Multi-Agent Code Review system into **NEXARION** — a production-grade developer platform featuring:
* A modern **FastAPI** backend with REST endpoints for authentication, reviews, pull requests, agent toggles, and provider tests.
* **Dual-Provider LLM Integration**: Supporting both **Ollama** (local offline inference with Qwen 2.5 Coder) and **NVIDIA Nemotron** (cloud inference via NVIDIA NIM API).
* A **PostgreSQL** relational schema for persistent users, pull requests, review executions, and structured findings.
* **Cloudinary** integration for secure profile avatar uploads.
* A handcrafted **React + TypeScript + Vite** frontend matching the supplied design assets:
  - White geometric NEXARION logo.
  - Animated iridescent `AIOrb` responding to real review states (`idle`, `reviewing`, `success`, `error`).
  - Contextual dynamic greeting based on local time and user profile.
  - Neon-edged glowing review composer with diff attachment and live provider switching.
  - 5 core pages: Overview, Pull Requests, AI Agents, Review History, and Settings.
  - Neutral brand-consistent status indicators (avoiding harsh green/red language).

---

## 2. File & Component Breakdown

| File / Component | Purpose |
| :--- | :--- |
| `src/code_review/config.py` | Settings updated with database, NVIDIA, Cloudinary, and Auth fields |
| `src/code_review/llm/nemotron_client.py` | NVIDIA NIM REST client using standard library `urllib` |
| `src/code_review/llm/factory.py` | Provider factory returning OllamaClient or NemotronClient |
| `src/code_review/llm/__init__.py` | Exported NemotronClient and get_llm_client |
| `src/code_review/agents/llm_agent.py` | LLMAgent updated to support provider selection |
| `src/code_review/orchestrator.py` | ReviewOrchestrator updated with `llm_provider` parameter |
| `src/code_review/db/database.py` | SQLAlchemy engine, session maker, and DB dependency |
| `src/code_review/db/models.py` | ORM models: User, Repository, PullRequest, Review, Finding, AgentConfig |
| `src/code_review/db/init_db.py` | Database initialization and seeding script |
| `src/code_review/web/auth.py` | JWT token handling and bcrypt password hashing |
| `src/code_review/web/schemas.py` | Pydantic request/response schemas |
| `src/code_review/web/routes/*.py` | Endpoints: auth, reviews, pull requests, agents, providers, user |
| `src/code_review/web/app.py` | FastAPI application with CORS and SPA static serving |
| `frontend/src/index.css` | Design system tokens, neon glow, and muted status styles |
| `frontend/src/components/layout/Logo.tsx` | Geometric NEXARION logo SVG component |
| `frontend/src/components/orb/AIOrb.tsx` | Reusable animated iridescent AI orb |
| `frontend/src/components/reviews/ReviewComposer.tsx` | Glowing neon-edged review composer |
| `frontend/src/components/reviews/ReviewDetailModal.tsx` | Findings inspector with diff viewer |
| `frontend/src/pages/*.tsx` | 5 application pages: Overview, PRs, Agents, History, Settings |
| `tests/test_web_api.py` | 7 unit tests covering health, providers, agents, PRs, reviews |

---

## 3. Database Schema (PostgreSQL)

Tables created and managed in `nexarion_db`:
1. `users`: Stores user identity, bcrypt password hash, avatar URL, theme, plan, and GitHub status.
2. `repositories`: Repositories tracked for pull requests.
3. `pull_requests`: PR records with branches, status (`open`, `merged`, `closed`, `draft`), and changed lines stats.
4. `reviews`: Review executions with duration, findings count, critical status, provider, and model used.
5. `findings`: Individual findings linked to reviews with file path, line numbers, description, severity, rule ID, and suggested fixes.
6. `agent_configs`: Active agent configuration and toggles.

---

## 4. Verification & Quality Gates

* **Pytest Suite**: 260/260 passing tests (including 7 new web API tests).
* **Ruff Linter**: Clean with 0 errors across `src/` and `tests/`.
* **Frontend Build**: `tsc -b && vite build` built in 3.8s with zero errors.
* **Browser Verification**: Navigated through Overview, Pull Requests, Agents, Review History, and Settings. Successfully ran sample diff review and inspected findings in the ReviewDetailModal.
