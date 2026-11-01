import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from code_review.db.database import get_db
from code_review.db.models import FindingRecord, UserRecord
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.models.review import ReviewResult
from code_review.web.app import app
from code_review.web.auth import create_access_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_a() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="test_user_a@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="test_user_a@nexarion.dev",
            name="User Alpha",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def user_b() -> UserRecord:
    db = next(get_db())
    user = db.query(UserRecord).filter_by(email="test_user_b@nexarion.dev").first()
    if not user:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email="test_user_b@nexarion.dev",
            name="User Beta",
            github_connected=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def auth_headers_a(user_a: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_a.id, "email": user_a.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_b(user_b: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user_b.id, "email": user_b.email})
    return {"Authorization": f"Bearer {token}"}


def test_health_check_endpoint(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "NEXARION"
    assert "active_provider" in data


def test_list_providers_endpoint(client: TestClient) -> None:
    resp = client.get("/api/providers/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    providers = {p["provider"]: p for p in data["providers"]}
    assert "ollama" in providers
    assert "llm" in providers or "nvidia" in providers


def test_list_agents_endpoint(client: TestClient) -> None:
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    agent_ids = [a["agent_id"] for a in data]
    assert "security" in agent_ids
    assert "quality" in agent_ids
    assert "performance" in agent_ids


def test_update_agent_toggle(client: TestClient) -> None:
    resp = client.put("/api/agents/security", json={"is_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    resp2 = client.put("/api/agents/security", json={"is_enabled": True})
    assert resp2.status_code == 200
    assert resp2.json()["is_enabled"] is True


def test_pull_requests_unauthenticated_rejected(client: TestClient) -> None:
    resp = client.get("/api/pull-requests")
    assert resp.status_code == 401


def test_pull_requests_github_disconnected(
    client: TestClient, auth_headers_a: dict[str, str], user_a: UserRecord
) -> None:
    db = next(get_db())
    u = db.query(UserRecord).filter_by(id=user_a.id).first()
    u.github_connected = False
    u.github_token = None
    db.commit()

    resp = client.get("/api/pull-requests", headers=auth_headers_a)
    assert resp.status_code == 400
    assert "GitHub account is not connected" in resp.json()["detail"]


def test_pull_requests_real_data_and_filters(
    client: TestClient, auth_headers_a: dict[str, str], user_a: UserRecord
) -> None:
    db = next(get_db())
    u = db.query(UserRecord).filter_by(id=user_a.id).first()
    u.github_connected = True
    u.github_token = "ghp_real_token_mock_123"
    db.commit()

    mock_raw_prs = [
        {
            "number": 101,
            "title": "Real Open Feature",
            "author": "dev-user",
            "head_branch": "feature/branch",
            "base_branch": "main",
            "state": "open",
            "created_at": "2026-10-26T10:00:00Z",
        },
        {
            "number": 102,
            "title": "Real Merged Fix",
            "author": "dev-user",
            "head_branch": "fix/bug",
            "base_branch": "main",
            "state": "merged",
            "created_at": "2026-10-25T10:00:00Z",
        },
        {
            "number": 103,
            "title": "Real Closed PR",
            "author": "dev-user",
            "head_branch": "discarded/branch",
            "base_branch": "main",
            "state": "closed",
            "created_at": "2026-10-24T10:00:00Z",
        },
    ]

    with patch("code_review.web.routes.pr_routes.GitHubService") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh.list_repositories.return_value = [
            {"owner": "owner", "name": "real-repo", "full_name": "owner/real-repo"}
        ]
        mock_gh.list_pull_requests.return_value = mock_raw_prs
        mock_gh_cls.return_value = mock_gh

        resp = client.get("/api/pull-requests", headers=auth_headers_a)
        assert resp.status_code == 200
        prs = resp.json()
        assert len(prs) == 3
        assert prs[0]["status"] == "open"
        assert prs[1]["status"] == "merged"
        assert prs[2]["status"] == "closed"

        resp_open = client.get("/api/pull-requests?status=open", headers=auth_headers_a)
        assert resp_open.status_code == 200
        open_prs = resp_open.json()
        assert len(open_prs) == 1
        assert open_prs[0]["pr_number"] == 101

        resp_merged = client.get("/api/pull-requests?status=merged", headers=auth_headers_a)
        assert resp_merged.status_code == 200
        merged_prs = resp_merged.json()
        assert len(merged_prs) == 1
        assert merged_prs[0]["pr_number"] == 102


@patch("code_review.web.routes.review_routes.ReviewOrchestrator")
def test_create_and_get_review(
    mock_orchestrator_cls, client: TestClient, auth_headers_a: dict[str, str]
) -> None:
    mock_instance = MagicMock()
    mock_finding = Finding(
        file="auth.py",
        line=42,
        message="Hardcoded password detected",
        severity=Severity.ERROR,
        category=Category.SECURITY,
        agent=AgentType.BANDIT,
        rule_id="B105",
        suggestion="Use environment variable instead.",
    )
    mock_instance.review_diff.return_value = ReviewResult(
        findings=[mock_finding],
        files_reviewed=1,
    )
    mock_agent = MagicMock()
    mock_agent.name = "bandit"
    mock_instance.agents = [mock_agent]
    mock_orchestrator_cls.return_value = mock_instance

    diff = "--- a/auth.py\n+++ b/auth.py\n@@ -40,3 +40,3 @@\n+SECRET = '12345'\n"
    resp = client.post(
        "/api/reviews",
        json={
            "diff_text": diff,
            "title": "Test PR Review",
            "repository_name": "real-owner/my-repo",
            "provider": "nvidia",
            "include_llm": False,
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test PR Review"
    assert data["finding_count"] == 1
    assert len(data["findings"]) == 1

    review_id = data["id"]
    get_resp = client.get(f"/api/reviews/{review_id}", headers=auth_headers_a)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == review_id


@patch("code_review.web.routes.review_routes.ReviewOrchestrator")
def test_review_deletion_and_cascade(
    mock_orchestrator_cls, client: TestClient, auth_headers_a: dict[str, str]
) -> None:
    mock_instance = MagicMock()
    mock_finding = Finding(
        file="db.py",
        line=12,
        message="SQL Injection risk",
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        agent=AgentType.BANDIT,
        rule_id="B608",
    )
    mock_instance.review_diff.return_value = ReviewResult(
        findings=[mock_finding],
        files_reviewed=1,
    )
    mock_agent = MagicMock()
    mock_agent.name = "bandit"
    mock_instance.agents = [mock_agent]
    mock_orchestrator_cls.return_value = mock_instance

    sample_diff = "--- a/db.py\n+++ b/db.py\n@@ -1,1 +1,1 @@\n+query = f'SELECT * FROM users'\n"
    create_resp = client.post(
        "/api/reviews",
        json={
            "diff_text": sample_diff,
            "title": "Review To Delete",
        },
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 200
    review_id = create_resp.json()["id"]

    db = next(get_db())
    findings = db.query(FindingRecord).filter_by(review_id=review_id).all()
    assert len(findings) == 1

    del_resp = client.delete(f"/api/reviews/{review_id}", headers=auth_headers_a)
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/reviews/{review_id}", headers=auth_headers_a)
    assert get_resp.status_code == 404

    findings_after = db.query(FindingRecord).filter_by(review_id=review_id).all()
    assert len(findings_after) == 0


@patch("code_review.web.routes.review_routes.ReviewOrchestrator")
def test_review_user_isolation(
    mock_orchestrator_cls,
    client: TestClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    mock_instance = MagicMock()
    mock_instance.review_diff.return_value = ReviewResult(findings=[], files_reviewed=1)
    mock_instance.agents = []
    mock_orchestrator_cls.return_value = mock_instance

    create_resp = client.post(
        "/api/reviews",
        json={
            "diff_text": "--- a/main.py\n+++ b/main.py\n+x=1\n",
            "title": "User A Private Review",
        },
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 200
    user_a_review_id = create_resp.json()["id"]

    b_list = client.get("/api/reviews", headers=auth_headers_b)
    assert b_list.status_code == 200
    b_reviews = b_list.json()
    assert not any(r["id"] == user_a_review_id for r in b_reviews)

    b_get = client.get(f"/api/reviews/{user_a_review_id}", headers=auth_headers_b)
    assert b_get.status_code == 404

    b_del = client.delete(f"/api/reviews/{user_a_review_id}", headers=auth_headers_b)
    assert b_del.status_code == 404

    a_get = client.get(f"/api/reviews/{user_a_review_id}", headers=auth_headers_a)
    assert a_get.status_code == 200
    assert a_get.json()["id"] == user_a_review_id


def test_conversations_user_isolation(
    client: TestClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    create_resp = client.post(
        "/api/conversations",
        json={"title": "User A Chat", "initial_message": "Hello from User A"},
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 201
    conv_a = create_resp.json()
    conv_a_id = conv_a["id"]

    b_list = client.get("/api/conversations", headers=auth_headers_b)
    assert b_list.status_code == 200
    b_convs = b_list.json()
    assert not any(c["id"] == conv_a_id for c in b_convs)

    b_get = client.get(f"/api/conversations/{conv_a_id}", headers=auth_headers_b)
    assert b_get.status_code == 404

    b_del = client.delete(f"/api/conversations/{conv_a_id}", headers=auth_headers_b)
    assert b_del.status_code == 404

    a_del = client.delete(f"/api/conversations/{conv_a_id}", headers=auth_headers_a)
    assert a_del.status_code == 204

    a_get = client.get(f"/api/conversations/{conv_a_id}", headers=auth_headers_a)
    assert a_get.status_code == 404


@patch("code_review.web.routes.conversation_routes._generate_assistant_reply")
def test_guest_conversation_support_and_isolation(
    mock_reply,
    client: TestClient,
    auth_headers_a: dict[str, str],
) -> None:
    mock_reply.return_value = "Hello! I am NEXARION AI."

    guest_resp = client.post(
        "/api/conversations",
        json={"title": "Guest Chat", "initial_message": "Hello from guest"},
    )
    assert guest_resp.status_code == 201
    guest_conv = guest_resp.json()
    guest_conv_id = guest_conv["id"]

    guest_list = client.get("/api/conversations")
    assert guest_list.status_code == 200
    assert guest_list.json() == []

    a_list = client.get("/api/conversations", headers=auth_headers_a)
    assert a_list.status_code == 200
    assert not any(c["id"] == guest_conv_id for c in a_list.json())

    a_get = client.get(f"/api/conversations/{guest_conv_id}", headers=auth_headers_a)
    assert a_get.status_code == 404

    g_get = client.get(f"/api/conversations/{guest_conv_id}")
    assert g_get.status_code == 200
    assert g_get.json()["id"] == guest_conv_id

    g_del = client.delete(f"/api/conversations/{guest_conv_id}")
    assert g_del.status_code == 204


@patch("code_review.web.routes.review_routes.ReviewOrchestrator")
def test_overview_metrics_data_driven(
    mock_orchestrator_cls,
    client: TestClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    m_resp_a = client.get("/api/overview/metrics", headers=auth_headers_a)
    assert m_resp_a.status_code == 200
    metrics_a = m_resp_a.json()
    initial_reviews_count = metrics_a["total_reviews"]
    initial_findings_count = metrics_a["total_findings"]

    mock_instance = MagicMock()
    mock_finding = Finding(
        file="crypto.py",
        line=10,
        message="Weak hashing algorithm (MD5)",
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        agent=AgentType.BANDIT,
        rule_id="B303",
    )
    mock_instance.review_diff.return_value = ReviewResult(
        findings=[mock_finding], files_reviewed=1
    )
    mock_instance.agents = []
    mock_orchestrator_cls.return_value = mock_instance

    create_resp = client.post(
        "/api/reviews",
        json={
            "diff_text": "--- a/crypto.py\n+++ b/crypto.py\n+hash=md5()\n",
            "title": "Crypto Review",
        },
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 200
    review_id = create_resp.json()["id"]

    m_resp_a2 = client.get("/api/overview/metrics", headers=auth_headers_a)
    assert m_resp_a2.status_code == 200
    metrics_a2 = m_resp_a2.json()
    assert metrics_a2["total_reviews"] == initial_reviews_count + 1
    assert metrics_a2["total_findings"] == initial_findings_count + 1
    assert "active_agents_count" in metrics_a2
    assert "total_agents_count" in metrics_a2

    m_resp_b = client.get("/api/overview/metrics", headers=auth_headers_b)
    assert m_resp_b.status_code == 200
    metrics_b = m_resp_b.json()
    assert metrics_b["total_reviews"] == 0

    del_resp = client.delete(f"/api/reviews/{review_id}", headers=auth_headers_a)
    assert del_resp.status_code == 204

    m_resp_a3 = client.get("/api/overview/metrics", headers=auth_headers_a)
    assert m_resp_a3.status_code == 200
    metrics_a3 = m_resp_a3.json()
    assert metrics_a3["total_reviews"] == initial_reviews_count
    assert metrics_a3["total_findings"] == initial_findings_count


def test_user_profile_and_avatar(client: TestClient, auth_headers_a: dict[str, str]) -> None:
    resp = client.get("/api/users/me", headers=auth_headers_a)
    assert resp.status_code == 200
    user_data = resp.json()
    assert user_data["email"] == "test_user_a@nexarion.dev"

    update_resp = client.put(
        "/api/users/me", json={"name": "Alpha Updated"}, headers=auth_headers_a
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Alpha Updated"

    invalid_file = ("test.txt", b"not an image", "text/plain")
    fail_upload = client.post(
        "/api/users/me/avatar", files={"file": invalid_file}, headers=auth_headers_a
    )
    assert fail_upload.status_code == 400

    valid_png = (
        "avatar.png",
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82",
        "image/png",
    )
    success_upload = client.post(
        "/api/users/me/avatar", files={"file": valid_png}, headers=auth_headers_a
    )
    assert success_upload.status_code == 200
    assert success_upload.json()["avatar_url"] is not None


def test_github_endpoints(client: TestClient, auth_headers_a: dict[str, str]) -> None:
    status_resp = client.get("/api/github/status", headers=auth_headers_a)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "connected" in status_data
    assert "configured" in status_data

    auth_url_resp = client.get("/api/github/auth-url")
    assert auth_url_resp.status_code == 200
    assert "url" in auth_url_resp.json()

    disconnect_resp = client.post("/api/github/disconnect", headers=auth_headers_a)
    assert disconnect_resp.status_code == 200
    assert disconnect_resp.json()["connected"] is False
