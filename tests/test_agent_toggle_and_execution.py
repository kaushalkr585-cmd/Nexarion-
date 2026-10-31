"""Tests for Nexarion agent toggle responsiveness, database persistence,
orchestration enforcement, and disabled-agent execution prevention.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from code_review.agents.ast_agent import ASTAgent
from code_review.agents.bandit_agent import BanditAgent
from code_review.agents.registry import (
    build_active_agents,
    get_persisted_enabled_agent_ids,
    invalidate_agent_config_cache,
    is_agent_enabled,
)
from code_review.agents.ruff_agent import RuffAgent
from code_review.db.database import get_db
from code_review.db.models import AgentConfigRecord, UserRecord
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.app import app
from code_review.web.auth import create_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> Session:
    db = next(get_db())
    try:
        yield db
    finally:
        pass


@pytest.fixture
def auth_headers(db_session: Session) -> dict[str, str]:
    user = db_session.query(UserRecord).filter_by(email="agent_tester@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="agent_tester@nexarion.dev",
            name="Agent Tester",
            github_connected=False,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.id, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def ensure_default_agents(db_session: Session):
    """Ensure agent configs are seeded in the database before each test."""
    invalidate_agent_config_cache()
    defaults = [
        ("ast", "AST Structural Analysis", True, "deterministic"),
        ("ruff", "Code Quality & Linter", True, "deterministic"),
        ("security", "Security & Vulnerability", True, "deterministic"),
        ("performance", "Performance & Complexity", True, "deterministic"),
        ("documentation", "Documentation & Types", True, "deterministic"),
        ("test", "Test Coverage Analysis", True, "deterministic"),
        ("semantic", "Semantic Reasoning", True, "deterministic"),
    ]
    for agent_id, name, is_enabled, provider in defaults:
        record = db_session.query(AgentConfigRecord).filter_by(agent_id=agent_id).first()
        if not record:
            record = AgentConfigRecord(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                name=name,
                description=f"{name} agent engine",
                is_enabled=is_enabled,
                provider=provider,
            )
            db_session.add(record)
        else:
            record.is_enabled = is_enabled
    db_session.commit()
    invalidate_agent_config_cache()
    yield
    # Reset all agents to enabled after test
    for record in db_session.query(AgentConfigRecord).all():
        record.is_enabled = True
    db_session.commit()
    invalidate_agent_config_cache()


# -----------------------------------------------------------------------------
# Scenario A: Instant Toggle & Database Persistence
# -----------------------------------------------------------------------------
def test_scenario_a_instant_toggle(client: TestClient, db_session: Session):
    """Click Security Agent OFF -> backend updates DB, returns enabled=False."""
    # 1. Update through API
    resp = client.put("/api/agents/security", json={"is_enabled": False})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["agent_id"] == "security"
    assert data["is_enabled"] is False

    # 2. Verify directly from database
    record = db_session.query(AgentConfigRecord).filter_by(agent_id="security").first()
    assert record is not None
    assert record.is_enabled is False


# -----------------------------------------------------------------------------
# Scenario B: Disabled Agent Execution Prevention
# -----------------------------------------------------------------------------
def test_scenario_b_disabled_agent_never_executes(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
):
    """Disable Security Agent -> initiating review NEVER invokes BanditAgent."""
    # 1. Disable security agent via API
    resp = client.put("/api/agents/security", json={"is_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    # 2. Verify registry and orchestrator exclude BanditAgent
    enabled_ids = get_persisted_enabled_agent_ids(db_session, use_cache=False)
    assert "security" not in enabled_ids
    assert "bandit" not in enabled_ids

    active_agents = build_active_agents(enabled_ids)
    assert not any(isinstance(a, BanditAgent) for a in active_agents)
    assert not any(is_agent_enabled(BanditAgent(), enabled_ids) for _ in [1])

    # 3. Create review via API on diff with hardcoded MD5 vulnerability
    vulnerable_diff = """--- a/crypto.py
+++ b/crypto.py
@@ -0,0 +1,5 @@
+import hashlib
+
+def insecure_hash(data):
+    return hashlib.md5(data.encode()).hexdigest()
+"""
    review_resp = client.post(
        "/api/reviews",
        json={
            "diff_text": vulnerable_diff,
            "title": "Vulnerability Test with Disabled Security Agent",
            # Even if a malicious or stale client explicitly requests "security" agent:
            "selected_agents": ["security", "ast", "ruff"],
        },
        headers=auth_headers,
    )
    assert review_resp.status_code == 200, review_resp.text
    review_data = review_resp.json()

    # 4. Verify Bandit was NOT used in review
    assert "bandit" not in review_data["agents_used"]
    assert "security" not in review_data["agents_used"]

    # 5. Verify NO findings came from Bandit/Security Agent
    for finding in review_data["findings"]:
        assert finding["agent"] not in ("bandit", "security")
        assert finding.get("agent_id") not in ("bandit", "security")


# -----------------------------------------------------------------------------
# Scenario C: Enabled Agent Execution
# -----------------------------------------------------------------------------
def test_scenario_c_enabled_agent_executes(client: TestClient, auth_headers: dict[str, str]):
    """Enable Security Agent -> BanditAgent executes and flags security vulnerabilities."""
    # 1. Ensure security is enabled
    client.put("/api/agents/security", json={"is_enabled": True})

    vulnerable_diff = """--- a/tests/fixtures/sample_security.py
+++ b/tests/fixtures/sample_security.py
@@ -16,4 +16,4 @@
 def execute_dynamic_code(code_string: str) -> None:
-    pass
+    eval(code_string)
"""
    review_resp = client.post(
        "/api/reviews",
        json={
            "diff_text": vulnerable_diff,
            "title": "Vulnerability Test with Enabled Security Agent",
        },
        headers=auth_headers,
    )
    assert review_resp.status_code == 200
    review_data = review_resp.json()

    # Bandit should be in agents_used
    assert "bandit" in review_data["agents_used"]
    # Should flag security vulnerability
    assert any(f["category"].lower() == "security" for f in review_data["findings"])


# -----------------------------------------------------------------------------
# Scenario D: Persistence Across Sessions
# -----------------------------------------------------------------------------
def test_scenario_d_persistence(client: TestClient, db_session: Session):
    """Disable Security Agent -> remains disabled across fresh DB sessions and queries."""
    client.put("/api/agents/security", json={"is_enabled": False})

    # Fresh session
    new_db = next(get_db())
    enabled_ids = get_persisted_enabled_agent_ids(new_db, use_cache=False)
    assert "security" not in enabled_ids
    assert "bandit" not in enabled_ids

    # Listing agents confirms persistence
    list_resp = client.get("/api/agents")
    sec_item = next(a for a in list_resp.json() if a["agent_id"] == "security")
    assert sec_item["is_enabled"] is False


# -----------------------------------------------------------------------------
# Scenario E: Rapid Toggle Sequence Resolution
# -----------------------------------------------------------------------------
def test_scenario_e_rapid_toggle(client: TestClient, db_session: Session):
    """Toggle agent rapidly -> final DB and cache state matches last request."""
    # Sequence of rapid toggles: False -> True -> False
    client.put("/api/agents/security", json={"is_enabled": False})
    client.put("/api/agents/security", json={"is_enabled": True})
    last_resp = client.put("/api/agents/security", json={"is_enabled": False})
    assert last_resp.json()["is_enabled"] is False

    enabled_ids = get_persisted_enabled_agent_ids(db_session, use_cache=True)
    assert "security" not in enabled_ids

    # Now toggle back to True
    client.put("/api/agents/security", json={"is_enabled": True})
    enabled_ids = get_persisted_enabled_agent_ids(db_session, use_cache=True)
    assert "security" in enabled_ids


# -----------------------------------------------------------------------------
# Scenario F: Multiple Agent Combinations & Empty Execution Pipeline
# -----------------------------------------------------------------------------
def test_scenario_f_single_agent_and_empty_pipeline(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
):
    """Disable all agents except Ruff -> only Ruff runs.
    Disable ALL agents -> pipeline executes cleanly in 0.0s with 0 findings.
    """
    # 1. Disable all except ruff
    for record in db_session.query(AgentConfigRecord).all():
        record.is_enabled = (record.agent_id == "ruff")
    db_session.commit()
    invalidate_agent_config_cache()

    sample_diff = """--- a/clean.py
+++ b/clean.py
@@ -0,0 +1,2 @@
+import os
+x = 1
+"""
    resp = client.post(
        "/api/reviews",
        json={"diff_text": sample_diff, "title": "Ruff Only Review"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_used"] == ["ruff"]

    # 2. Disable ALL agents (including ruff)
    for record in db_session.query(AgentConfigRecord).all():
        record.is_enabled = False
    db_session.commit()
    invalidate_agent_config_cache()

    resp_empty = client.post(
        "/api/reviews",
        json={"diff_text": sample_diff, "title": "All Agents Disabled"},
        headers=auth_headers,
    )
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert data_empty["agents_used"] == []
    assert data_empty["finding_count"] == 0
    assert len(data_empty["findings"]) == 0


# -----------------------------------------------------------------------------
# Scenario G: Concurrent Reviews with Snapshot Isolation
# -----------------------------------------------------------------------------
def test_scenario_g_concurrent_reviews_snapshot_isolation():
    """Two concurrent reviews with different enabled_agent_ids execute independently
    without cross-contaminating agent pipelines.
    """
    orch_1 = ReviewOrchestrator(enabled_agent_ids={"ast"})
    orch_2 = ReviewOrchestrator(enabled_agent_ids={"ast", "ruff"})

    assert {a.name for a in orch_1.active_agents} == {"ast"}
    assert {a.name for a in orch_2.active_agents} == {"ast", "ruff"}

    assert orch_1.is_agent_enabled(ASTAgent()) is True
    assert orch_1.is_agent_enabled(RuffAgent()) is False
    assert orch_2.is_agent_enabled(ASTAgent()) is True
    assert orch_2.is_agent_enabled(RuffAgent()) is True

    diff = """--- a/test.py
+++ b/test.py
@@ -0,0 +1,2 @@
+x = 1
+"""
    res1 = orch_1.review_diff(diff)
    res2 = orch_2.review_diff(diff)

    assert res1.files_reviewed == 1
    assert res2.files_reviewed == 1
