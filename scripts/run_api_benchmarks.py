import json
import statistics
import time

from fastapi.testclient import TestClient

from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.ruff_agent import RuffAgent
from code_review.db.database import get_session_factory
from code_review.db.models import UserRecord
from code_review.orchestrator import ReviewOrchestrator
from code_review.parsers.diff_parser import parse_diff
from code_review.web.app import create_app
from code_review.web.auth import create_access_token

SAMPLE_DIFF = """--- a/src/auth_service.py
+++ b/src/auth_service.py
@@ -25,6 +25,10 @@ def login(username, password, db):
-    query = text("SELECT id, role FROM users WHERE username = :u AND password = :p")
-    return db.execute(query, {"u": username, "p": hash_pwd(password)}).first()
+    # Legacy bypass for admin inspection
+    raw_query = f"SELECT id FROM users WHERE u = '{username}' AND p = '{password}'"
+    return db.execute(text(raw_query)).first()
+
+    # Hardcoded fallback token
+    BACKDOOR_KEY = "super_admin_secret_token_12345"
"""


def run_benchmarks():
    print("=" * 80)
    print("NEXARION API & ENGINE EMPIRICAL PERFORMANCE BENCHMARKS")
    print("=" * 80)

    app = create_app()
    client = TestClient(app)

    client.get("/api/health")

    session_factory = get_session_factory()
    with session_factory() as db:
        user = db.query(UserRecord).first()
        user_id = user.id if user else "test-user-id"
    token = create_access_token({"sub": user_id})
    auth_headers = {"Authorization": f"Bearer {token}"}

    results = []

    def measure(category, name, func, iterations=20):
        try:
            func()
        except Exception:
            pass

        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            func()
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000.0)

        avg = statistics.mean(times)
        median = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else avg
        p99 = sorted(times)[int(len(times) * 0.99)] if len(times) > 1 else avg
        min_t = min(times)
        max_t = max(times)
        rps = 1000.0 / avg if avg > 0 else 0

        row = {
            "category": category,
            "name": name,
            "mean_ms": round(avg, 2),
            "median_ms": round(median, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "min_ms": round(min_t, 2),
            "max_ms": round(max_t, 2),
            "est_rps": round(rps, 1),
        }
        results.append(row)
        msg = (
            f"[{category}] {name:<36} | {avg:6.2f}ms avg | "
            f"{median:6.2f}ms med | {p95:6.2f}ms p95 | {rps:7.1f} req/s"
        )
        print(msg)
        return row

    print("\n[Phase 1] Core In-Memory Engine Microbenchmarks:")
    print("-" * 80)
    diff_files = parse_diff(SAMPLE_DIFF)
    ast_agent = ASTAgent()
    bandit_agent = BanditAgent()
    ruff_agent = RuffAgent()
    orchestrator = ReviewOrchestrator(include_llm=False, parallel=True)

    measure(
        "Engine",
        "Unified Diff Parser (parse_diff)",
        lambda: parse_diff(SAMPLE_DIFF),
        iterations=100,
    )
    measure(
        "Engine",
        "AST Semantic Analysis (ASTAgent)",
        lambda: ast_agent.review(diff_files),
        iterations=50,
    )
    measure(
        "Engine",
        "Bandit Security Scanner (BanditAgent)",
        lambda: bandit_agent.review(diff_files),
        iterations=50,
    )
    measure(
        "Engine",
        "Ruff Linter Rule Scanner (RuffAgent)",
        lambda: ruff_agent.review(diff_files),
        iterations=50,
    )
    measure(
        "Engine",
        "Parallel Multi-Agent Dispatch",
        lambda: orchestrator.review_diff(SAMPLE_DIFF),
        iterations=25,
    )

    print("\n[Phase 2] Database & CRUD API Endpoints:")
    print("-" * 80)
    measure("FastAPI", "GET /api/health", lambda: client.get("/api/health"), iterations=50)
    measure(
        "FastAPI",
        "GET /api/auth/me (JWT Auth)",
        lambda: client.get("/api/auth/me", headers=auth_headers),
        iterations=30,
    )
    measure(
        "FastAPI",
        "GET /api/overview/metrics (SQL)",
        lambda: client.get("/api/overview/metrics", headers=auth_headers),
        iterations=30,
    )
    measure(
        "FastAPI",
        "GET /api/agents (Agent Configs)",
        lambda: client.get("/api/agents", headers=auth_headers),
        iterations=30,
    )
    measure(
        "FastAPI",
        "GET /api/prs (Pull Requests)",
        lambda: client.get("/api/prs", headers=auth_headers),
        iterations=30,
    )
    measure(
        "FastAPI",
        "GET /api/reviews (Review History)",
        lambda: client.get("/api/reviews", headers=auth_headers),
        iterations=30,
    )
    measure(
        "FastAPI",
        "GET /api/conversations (Threads)",
        lambda: client.get("/api/conversations", headers=auth_headers),
        iterations=30,
    )

    print("\n[Phase 3] High-Load Endpoints (Execution & Persistence):")
    print("-" * 80)
    measure(
        "FastAPI",
        "POST /api/reviews (Multi-Agent)",
        lambda: client.post(
            "/api/reviews",
            json={
                "diff_text": SAMPLE_DIFF,
                "title": "Benchmark Review",
                "repository_name": "nexarion/benchmark",
                "provider": "ollama",
                "include_llm": False,
            },
            headers=auth_headers,
        ),
        iterations=15,
    )

    measure(
        "FastAPI",
        "POST /api/conversations (Create)",
        lambda: client.post(
            "/api/conversations", json={"title": "Benchmark Thread"}, headers=auth_headers
        ),
        iterations=15,
    )

    with open("docs/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nBenchmark results successfully exported to docs/benchmark_results.json")

if __name__ == "__main__":
    run_benchmarks()
