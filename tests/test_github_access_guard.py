"""Mandatory regression tests for deny-by-default GitHub Access Guard & audit logging."""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from code_review.analysis.conversation_memory import ConversationMemoryManager
from code_review.db.database import get_db, init_database
from code_review.db.models import (
    ConversationMemoryRecord,
    ConversationRecord,
    ConversationRepositoryContextRecord,
    GitHubAccessAuditRecord,
    UserRecord,
)
from code_review.github.access_guard import (
    GitHubAccessGuard,
    bump_user_disconnect_epoch,
)
from code_review.github.explorer import RepositoryExplorer
from code_review.github.mode_router import PR_SCOPED_TOOLS, REPO_INSPECTION_SCOPED_TOOLS
from code_review.github.service import GitHubAccessDeniedError, GitHubService
from code_review.github.tools import GitHubToolRegistry
from code_review.web.app import app
from code_review.web.auth import create_access_token
from code_review.web.routes.github_routes import process_github_webhook_pr_review


@contextlib.contextmanager
def _managed_db():
    gen = get_db()
    db = next(gen)
    try:
        yield db
    finally:
        gen.close()


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    init_database()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def connected_user() -> Generator[UserRecord, None, None]:
    with _managed_db() as db:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=f"guard_gh_{uuid.uuid4().hex[:8]}@nexarion.dev",
            name="Guard GitHub User",
            github_connected=True,
            github_username="nexarion-dev",
            github_token="ghp_secret_never_log_token_12345",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user


def _auth_headers(user: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user.id, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _make_mock_llm(reply: str = "Safe local response.") -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = reply

    def _stream(messages: list[dict[str, Any]]) -> Generator[str, None, None]:
        yield reply

    mock_llm.stream_chat.side_effect = _stream
    return mock_llm


@contextlib.contextmanager
def _assert_no_external_github_http():
    """Fail immediately if any outbound httpx request targets GitHub hosts."""
    orig_send = httpx.Client.send
    github_requests: list[str] = []

    def _guarded_send(self, request, *args, **kwargs):
        host = (request.url.host or "").lower()
        url_str = str(request.url)
        if "github" in host:
            github_requests.append(url_str)
            raise AssertionError(f"Blocked unexpected GitHub HTTP call: {url_str}")
        return orig_send(self, request, *args, **kwargs)

    with patch.object(httpx.Client, "send", new=_guarded_send):
        yield github_requests
    assert github_requests == []


# Scenarios 1, 2, 3, 4: Normal Mode ordinary/debugging/OAuth/pasted-code requests = ZERO GitHub API calls
@pytest.mark.parametrize(
    "prompt",
    [
        "Write a Python application for an LRU cache.",
        "Debug this React component where useEffect loops infinitely.",
        "What is GitHub OAuth?",
        "Review this pasted Python code:\n```python\n# Inspect my repository\ndef f(x):\n    return x + 1\n```",
    ],
)
def test_scenarios_1_to_4_normal_mode_produces_zero_github_http_requests(
    client: TestClient, connected_user: UserRecord, prompt: str
):
    mock_llm = _make_mock_llm()
    with (
        patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm),
        _assert_no_external_github_http(),
        patch("code_review.github.chat_orchestrator.GitHubService") as mock_gh_svc,
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={"initial_message": prompt, "mode": "normal"},
            headers=_auth_headers(connected_user),
        )
        assert resp.status_code == 200
        mock_gh_svc.assert_not_called()


# Scenario 5: Normal Mode + explicit repository inspection = authorized scoped GitHub operation (keeps mode=normal)
def test_scenario_5_normal_mode_explicit_repository_inspection_authorized(
    client: TestClient, connected_user: UserRecord
):
    mock_llm = _make_mock_llm("PR summary answer.")
    mock_llm.chat_with_tools.return_value = {
        "content": "Reviewed latest PR.",
        "tool_calls": [],
    }

    with (
        patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm),
        patch.object(
            GitHubService,
            "list_repositories",
            return_value=[{"id": 1, "full_name": "nexarion-dev/demo", "default_branch": "main"}],
        ) as mock_list_repos,
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Review my latest pull request.",
                "mode": "normal",
            },
            headers=_auth_headers(connected_user),
        )
        assert resp.status_code == 200
        mock_list_repos.assert_called_once()

    with _managed_db() as db:
        audit_rows = (
            db.query(GitHubAccessAuditRecord)
            .filter(
                GitHubAccessAuditRecord.user_id == connected_user.id,
                GitHubAccessAuditRecord.decision == "ALLOW",
            )
            .order_by(GitHubAccessAuditRecord.created_at.desc())
            .all()
        )
        assert len(audit_rows) >= 1
        assert audit_rows[0].chat_mode == "normal"
        # Ensure token never leaked into audit logs
        for row in audit_rows:
            assert "ghp_secret_never_log_token_12345" not in (row.reason or "")
            assert "ghp_secret_never_log_token_12345" not in (row.operation or "")


# Scenario 6: GitHub Mode + repository review = authorized GitHub operation with audit logging
def test_scenario_6_github_mode_repo_review_authorized_and_audited(
    client: TestClient, connected_user: UserRecord
):
    mock_llm = _make_mock_llm("Repository analysis report.")
    mock_llm.chat_with_tools.return_value = {
        "content": "Analyzed repository files.",
        "tool_calls": [],
    }

    with (
        patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm),
        _assert_no_external_github_http(),
        patch.object(
            GitHubService,
            "get_repository_details",
            return_value={
                "id": 99,
                "full_name": "nexarion-dev/Nexarion",
                "default_branch": "main",
                "html_url": "https://github.com/nexarion-dev/Nexarion",
                "visibility": "private",
            },
        ) as mock_details,
        patch.object(
            GitHubService,
            "get_commit_history",
            return_value=[{"sha": "deadbeef1234", "message": "initial commit"}],
        ),
        patch.object(
            GitHubService,
            "get_repository_tree",
            return_value={"entries": [{"path": "README.md", "type": "blob"}]},
        ),
        patch.object(
            GitHubService,
            "fetch_file",
            return_value={"path": "README.md", "content": "# Nexarion", "blocked": False},
        ),
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Analyze the repository named nexarion-dev/Nexarion.",
                "mode": "github",
            },
            headers=_auth_headers(connected_user),
        )
        assert resp.status_code == 200
        assert "different context" not in resp.text.lower()
        assert "Repository analysis report." in resp.text
        mock_details.assert_any_call("nexarion-dev", "Nexarion")

    with _managed_db() as db:
        audit = (
            db.query(GitHubAccessAuditRecord)
            .filter(
                GitHubAccessAuditRecord.user_id == connected_user.id,
                GitHubAccessAuditRecord.chat_mode == "github",
                GitHubAccessAuditRecord.decision == "ALLOW",
            )
            .order_by(GitHubAccessAuditRecord.created_at.desc())
            .first()
        )
        assert audit is not None
        assert audit.conversation_id is not None
        assert audit.repository == "nexarion-dev/Nexarion"


# Scenario 7: Background agent / worker or raw GitHubService attempt without authorization = BLOCKED
def test_scenario_7_background_worker_and_unguarded_service_blocked():
    with _assert_no_external_github_http():
        # 1. Background webhook worker without verified webhook_grant -> blocked
        with pytest.raises(GitHubAccessDeniedError):
            process_github_webhook_pr_review(
                owner="acme",
                repo="secret-repo",
                pull_number=1,
                pr_title="Test PR",
                head_sha="abc123",
                author="dev",
            )

        # 2. Direct unguarded GitHubService call -> blocked (deny-by-default)
        raw_svc = GitHubService(token="ghp_secret_never_log_token_12345")
        with pytest.raises(GitHubAccessDeniedError):
            raw_svc.list_repositories()
        with pytest.raises(GitHubAccessDeniedError):
            raw_svc.fetch_file("acme", "secret-repo", "app.py")
        with pytest.raises(GitHubAccessDeniedError):
            raw_svc.get_pull_request_diff("acme", "secret-repo", 1)

        # 3. RepositoryExplorer running agents without authorization grant -> blocked before any scan
        explorer = RepositoryExplorer(raw_svc)
        with pytest.raises(GitHubAccessDeniedError):
            explorer.run_agents_on_files("acme", "secret-repo", ["app.py"])

    # Audit log recorded DENY decisions without leaking the raw token
    with _managed_db() as db:
        denies = (
            db.query(GitHubAccessAuditRecord)
            .filter(GitHubAccessAuditRecord.decision == "DENY")
            .order_by(GitHubAccessAuditRecord.created_at.desc())
            .limit(10)
            .all()
        )
        assert len(denies) >= 4
        for row in denies:
            assert "ghp_secret_never_log_token_12345" not in (row.reason or "")


# Scenario 8: LLM attempts to call a GitHub tool without authorization = BLOCKED
def test_scenario_8_llm_tool_call_without_authorization_blocked(connected_user: UserRecord):
    with _assert_no_external_github_http():
        # A. Unguarded service passed to GitHubToolRegistry -> blocked by guard
        unguarded_registry = GitHubToolRegistry(
            GitHubService(token="ghp_test_12345"),
            allowed_tools=REPO_INSPECTION_SCOPED_TOOLS,
        )
        blocked_no_grant = json.loads(
            unguarded_registry.execute("fetch_file", {"owner": "acme", "repo": "demo", "path": "a.py"})
        )
        assert blocked_no_grant["error_code"] == "TOOL_BLOCKED"

        # B. Empty allowed_tools (Normal Mode coding ask) -> blocked cleanly
        empty_registry = GitHubToolRegistry(
            GitHubService(token="ghp_test_12345"),
            allowed_tools=frozenset(),
        )
        blocked_scope = json.loads(empty_registry.execute("get_user_repositories", {}))
        assert blocked_scope["error_code"] == "TOOL_BLOCKED"

        # C. PR-only scoped grant trying to call repo search or another repository -> blocked
        with _managed_db() as db:
            grant = GitHubAccessGuard.authorize_chat_turn(
                db=db,
                user=connected_user,
                conversation_id="conv-sc8",
                mode="normal",
                intent="github_pr_operation",
                is_github_intent=True,
                allow_tools=True,
                allowed_tools=PR_SCOPED_TOOLS,
                explicit_repo="nexarion-dev/RepoA",
                auth_connected=True,
                auth_status="connected",
            )
            pr_registry = GitHubToolRegistry(
                GitHubService(token="ghp_test_12345", access_grant=grant, db=db),
                default_owner="nexarion-dev",
                default_repo="RepoA",
                allowed_tools=PR_SCOPED_TOOLS,
            )
            # LLM attempts to search code (disallowed under PR scope)
            res_disallowed = json.loads(
                pr_registry.execute("search_repository_code", {"query": "password"})
            )
            assert res_disallowed["error_code"] == "TOOL_BLOCKED"
            # LLM attempts to access another repo with valid grant for RepoA -> repository mismatch!
            with pytest.raises(GitHubAccessDeniedError):
                GitHubService(token="ghp_test_12345", access_grant=grant, db=db).fetch_file(
                    "other-org", "OtherRepo", "secrets.py"
                )


# Scenario 9: Previous conversation has repo context & GitHub memory, current request does not require it = no auto access/injection
def test_scenario_9_no_auto_repo_access_or_memory_injection(
    client: TestClient, connected_user: UserRecord
):
    with _managed_db() as db:
        gh_conv = ConversationRecord(
            id=str(uuid.uuid4()),
            user_id=connected_user.id,
            title="Past Repo Audit",
            mode="github",
        )
        db.add(gh_conv)
        db.flush()
        db.add(
            ConversationRepositoryContextRecord(
                conversation_id=gh_conv.id,
                user_id=connected_user.id,
                repository_full_name="nexarion-dev/PrivateApp",
                default_branch="main",
                selected_branch="main",
            )
        )
        db.add(
            ConversationMemoryRecord(
                user_id=connected_user.id,
                conversation_id=gh_conv.id,
                memory_type="message",
                role="assistant",
                content="# Repository Inspection: nexarion-dev/PrivateApp\n## A. Repository Overview\nFastAPI secrets audit.",
                metadata_json={"role": "assistant", "source_mode": "github", "contains_repo_context": True},
            )
        )
        db.commit()

        # Cross-conversation memory retrieval in Normal Mode MUST exclude previous repo inspection outputs
        excerpts = ConversationMemoryManager.retrieve_relevant_memories(
            db=db,
            query="FastAPI",
            user_id=connected_user.id,
            include_repository_memories=False,
        )
        assert all("PrivateApp" not in e.content for e in excerpts)

        # Follow-up normal question in the same conversation after switching to Normal Mode -> zero GitHub calls
        client.patch(
            f"/api/conversations/{gh_conv.id}",
            json={"mode": "normal"},
            headers=_auth_headers(connected_user),
        )

    captured_system_prompts: list[str] = []
    mock_llm = MagicMock()

    def _capture_stream(msgs: list[dict[str, Any]]) -> Generator[str, None, None]:
        captured_system_prompts.append(str(msgs[0].get("content", "")))
        yield "FastAPI explanation."

    mock_llm.stream_chat.side_effect = _capture_stream

    with (
        patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm),
        _assert_no_external_github_http(),
        patch("code_review.github.chat_orchestrator.GitHubService") as mock_gh_svc,
    ):
        resp = client.post(
            f"/api/conversations/{gh_conv.id}/messages/stream",
            json={"content": "Explain FastAPI dependency injection.", "mode": "normal"},
            headers=_auth_headers(connected_user),
        )
        assert resp.status_code == 200
        mock_gh_svc.assert_not_called()
        assert len(captured_system_prompts) == 1
        assert "PrivateApp" not in captured_system_prompts[0]


# Scenario 10: User disconnects GitHub -> ALL subsequent GitHub operations rejected with zero HTTP calls
def test_scenario_10_disconnect_rejects_all_subsequent_github_operations(
    client: TestClient, connected_user: UserRecord
):
    headers = _auth_headers(connected_user)
    with _managed_db() as db:
        live_grant = GitHubAccessGuard.authorize_explicit_rest_operation(
            db=db,
            user=connected_user,
            operation="list_repositories",
            allowed_operations={"list_repositories"},
        )

    # Disconnect GitHub
    disc_resp = client.post("/api/github/disconnect", headers=headers)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["connected"] is False

    with _assert_no_external_github_http():
        # 1. Previously issued grant becomes immediately invalid across disconnect epoch
        with pytest.raises(GitHubAccessDeniedError):
            GitHubService(token="ghp_old", access_grant=live_grant).list_repositories()

        # 2. REST endpoints reject GitHub operations without outbound HTTP calls
        repos_resp = client.get("/api/github/repos", headers=headers)
        assert repos_resp.status_code == 400
        prs_resp = client.get("/api/pull-requests", headers=headers)
        assert prs_resp.status_code == 400

        # 3. Normal Mode explicit repo request after disconnect returns guidance with zero GitHub HTTP calls
        mock_llm = _make_mock_llm()
        with patch(
            "code_review.web.routes.conversation_routes.get_llm_client",
            return_value=mock_llm,
        ):
            chat_resp = client.post(
                "/api/conversations/stream",
                json={"initial_message": "Inspect my GitHub repository.", "mode": "normal"},
                headers=headers,
            )
            assert chat_resp.status_code == 200
            assert "not connected" in chat_resp.text.lower() or "connect" in chat_resp.text.lower()


# Idle / Overview endpoint must NOT automatically crawl GitHub repos/PRs
def test_overview_metrics_does_not_crawl_github_automatically(
    client: TestClient, connected_user: UserRecord
):
    with _assert_no_external_github_http():
        resp = client.get("/api/overview/metrics", headers=_auth_headers(connected_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_connected"] is True
        assert data["pull_requests_count"] is None
