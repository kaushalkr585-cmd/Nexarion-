import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from code_review.config import get_settings
from code_review.db.database import get_db
from code_review.db.models import (
    ConversationRecord,
    ConversationRepositoryContextRecord,
    GitHubConnectionRecord,
    UserRecord,
)
from code_review.github.auth_resolver import ensure_github_tables, resolve_user_github_context
from code_review.github.cache import get_github_cache
from code_review.github.chat_orchestrator import (
    GitHubChatOrchestrator,
    _match_repositories_to_prompt,
)
from code_review.github.explorer import RepositoryExplorer, detect_tech_stack
from code_review.github.service import (
    GitHubAuthError,
    GitHubService,
    is_ignored_repo_path,
    is_sensitive_repo_path,
)
from code_review.web.app import app
from code_review.web.auth import create_access_token
from code_review.web.crypto import decrypt_secret, encrypt_secret, is_encrypted


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user_one() -> UserRecord:
    db = next(get_db())
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=f"gh_chat_u1_{uuid.uuid4().hex[:8]}@nexarion.dev",
        name="GitHub Chat User 1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_two() -> UserRecord:
    db = next(get_db())
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=f"gh_chat_u2_{uuid.uuid4().hex[:8]}@nexarion.dev",
        name="GitHub Chat User 2",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _generate_test_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def test_credential_encryption_roundtrip_and_legacy_fallback():
    secret_val = "ghs_test_installation_token_123456"
    encrypted = encrypt_secret(secret_val)
    assert encrypted is not None
    assert encrypted != secret_val
    assert is_encrypted(encrypted)
    assert decrypt_secret(encrypted) == secret_val
    # Legacy plaintext token backward compatibility
    assert decrypt_secret("ghp_legacy_plaintext_token") == "ghp_legacy_plaintext_token"


def test_github_app_jwt_and_install_url(monkeypatch):
    pem = _generate_test_pem()
    settings = get_settings()
    monkeypatch.setattr(settings, "github_app_id", "123456")
    monkeypatch.setattr(settings, "github_app_slug", "nexarion-ai")
    monkeypatch.setattr(settings, "github_app_private_key", pem)

    svc = GitHubService()
    assert svc.is_github_app_configured() is True
    token_jwt = svc.create_app_jwt()
    assert isinstance(token_jwt, str) and token_jwt.count(".") == 2

    install_url = svc.get_app_install_url(state="test_state")
    assert "https://github.com/apps/nexarion-ai/installations/new" in install_url
    assert "state=test_state" in install_url


def test_github_app_callback_stores_encrypted_connection_and_syncs_user(
    client: TestClient, user_one: UserRecord, user_two: UserRecord, monkeypatch
):
    pem = _generate_test_pem()
    settings = get_settings()
    monkeypatch.setattr(settings, "github_app_id", "99999")
    monkeypatch.setattr(settings, "github_app_slug", "nexarion-ai")
    monkeypatch.setattr(settings, "github_app_private_key", pem)

    u1_token = create_access_token({"sub": user_one.id, "email": user_one.email})
    install_res = client.get(
        "/api/github/app/install-url?origin=http://localhost:5173",
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert install_res.status_code == 200
    state_param = install_res.json()["url"].split("state=")[-1]

    # Cross-user state mismatch must be rejected
    u2_token = create_access_token({"sub": user_two.id, "email": user_two.email})
    mismatch_res = client.get(
        f"/api/github/app/callback?installation_id=777&state={state_param}",
        headers={"Authorization": f"Bearer {u2_token}"},
        follow_redirects=False,
    )
    assert mismatch_res.status_code in (302, 307)
    assert "reason=state_mismatch" in mismatch_res.headers["location"]

    future_exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    with (
        patch.object(
            GitHubService,
            "create_installation_access_token",
            return_value={
                "token": "ghs_mock_install_secret_abc",
                "expires_at": future_exp,
                "permissions": {"contents": "read", "metadata": "read"},
            },
        ),
        patch.object(
            GitHubService,
            "get_installation_details",
            return_value={"id": 777, "account": {"id": 42, "login": "kaushalkr585-cmd"}},
        ),
    ):
        ok_res = client.get(
            f"/api/github/app/callback?installation_id=777&setup_action=install&state={state_param}",
            headers={"Authorization": f"Bearer {u1_token}"},
            follow_redirects=False,
        )
        assert ok_res.status_code in (302, 307)
        assert "github=connected" in ok_res.headers["location"]

    db = next(get_db())
    db.expire_all()
    conn = db.query(GitHubConnectionRecord).filter_by(user_id=user_one.id).first()
    assert conn is not None
    assert conn.auth_method == "github_app"
    assert conn.installation_id == "777"
    assert conn.github_username == "kaushalkr585-cmd"
    assert conn.connection_status == "connected"
    assert is_encrypted(conn.encrypted_access_token)
    assert decrypt_secret(conn.encrypted_access_token) == "ghs_mock_install_secret_abc"

    status_res = client.get(
        "/api/github/status",
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["connected"] is True
    assert body["auth_method"] == "github_app"
    assert body["connection_status"] == "connected"


def test_github_installation_token_auto_renewal_and_revocation():
    ensure_github_tables()
    db = next(get_db())
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=f"gh_renew_{uuid.uuid4().hex[:8]}@nexarion.dev",
        name="Renew Tester",
        github_connected=True,
    )
    db.add(user)
    db.flush()
    conn = GitHubConnectionRecord(
        user_id=user.id,
        auth_method="github_app",
        github_username="renew-user",
        installation_id="555111",
        encrypted_access_token=encrypt_secret("ghs_expired_old"),
        token_expires_at=datetime.now(UTC) - timedelta(minutes=5),
        connection_status="connected",
    )
    db.add(conn)
    db.commit()

    new_exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    with patch.object(
        GitHubService,
        "create_installation_access_token",
        return_value={"token": "ghs_fresh_token_xyz", "expires_at": new_exp, "permissions": {}},
    ):
        resolved = resolve_user_github_context(db, user)
        assert resolved.connected is True
        assert resolved.token == "ghs_fresh_token_xyz"

    # Now simulate expired + revoked installation
    conn.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    with patch.object(
        GitHubService,
        "create_installation_access_token",
        side_effect=GitHubAuthError("Installation deleted", error_code="GITHUB_FORBIDDEN"),
    ):
        revoked_res = resolve_user_github_context(db, user)
        assert revoked_res.connected is False
        assert revoked_res.connection_status == "revoked"


def test_path_security_filters_and_tech_stack_detection():
    assert is_sensitive_repo_path(".env") is True
    assert is_sensitive_repo_path(".env.production") is True
    assert is_sensitive_repo_path(".env.example") is False
    assert is_sensitive_repo_path("keys/private.pem") is True
    assert is_ignored_repo_path("frontend/node_modules/react/index.js") is True
    assert is_ignored_repo_path(".venv/Lib/site-packages/foo.py") is True
    assert is_ignored_repo_path("assets/logo.png") is True
    assert is_ignored_repo_path("src/code_review/web/app.py") is False

    stack = detect_tech_stack(
        [
            {"path": "src/main.py", "type": "blob"},
            {"path": "frontend/src/App.tsx", "type": "blob"},
            {"path": "Dockerfile", "type": "blob"},
        ],
        {
            "pyproject.toml": 'dependencies = ["fastapi", "sqlalchemy", "psycopg"]',
            "frontend/package.json": '{"dependencies": {"react": "^18.3.1"}, "devDependencies": {"vite": "^6.0.0"}}',
        },
    )
    assert "Python" in stack
    assert "FastAPI" in stack
    assert "SQLAlchemy" in stack
    assert "PostgreSQL" in stack
    assert "TypeScript" in stack
    assert "React" in stack
    assert "Vite" in stack
    assert "Docker" in stack


def test_explorer_runs_existing_agents_on_retrieved_repo_files():
    mock_svc = MagicMock(spec=GitHubService)
    insecure_py = (
        "import subprocess\ndef run_cmd(user_input):\n    subprocess.run(user_input, shell=True)\n"
    )
    mock_svc.fetch_file.return_value = {
        "path": "src/runner.py",
        "sha": "abc123",
        "size": len(insecure_py),
        "content": insecure_py,
        "blocked": False,
    }
    explorer = RepositoryExplorer(mock_svc)
    res = explorer.run_agents_on_files(
        "owner",
        "repo",
        ["src/runner.py", "../../etc/passwd"],
        ref="main",
        agent_ids=["security", "performance"],
    )
    assert res["files_analyzed"] == ["src/runner.py"]
    assert res["total_findings"] >= 1
    assert any(
        "subprocess" in f["message"].lower() or f["rule_id"] == "B602" for f in res["findings"]
    )


def test_repository_matching_and_disambiguation():
    repos = [
        {
            "id": 1,
            "name": "Nexarion-",
            "full_name": "kaushalkr585-cmd/Nexarion-",
            "default_branch": "main",
        },
        {
            "id": 2,
            "name": "Portfolio",
            "full_name": "kaushalkr585-cmd/Portfolio",
            "default_branch": "main",
        },
        {
            "id": 3,
            "name": "Diabetes-Prediction",
            "full_name": "kaushalkr585-cmd/Diabetes-Prediction",
            "default_branch": "main",
        },
    ]
    matched, ambiguous = _match_repositories_to_prompt("Inspect my Nexarion project", repos)
    assert matched is not None
    assert matched["full_name"] == "kaushalkr585-cmd/Nexarion-"
    assert ambiguous == []

    # Ambiguous generic prompt triggers candidates
    matched2, ambiguous2 = _match_repositories_to_prompt("Inspect my project please", repos)
    assert matched2 is None
    assert len(ambiguous2) == 3


def test_github_cache_isolates_users():
    cache = get_github_cache()
    cache.clear()
    k1 = cache.build_key("user:u1", "repo_details", repo="owner/private-repo")
    k2 = cache.build_key("user:u2", "repo_details", repo="owner/private-repo")
    assert k1 != k2
    cache.set(k1, {"secret": "user1-only"})
    assert cache.get(k1) == {"secret": "user1-only"}
    assert cache.get(k2) is None


def test_conversational_github_tool_orchestration_and_context_persistence():
    ensure_github_tables()
    db = next(get_db())
    user = UserRecord(
        id=str(uuid.uuid4()),
        email=f"gh_orch_{uuid.uuid4().hex[:8]}@nexarion.dev",
        name="Orch Tester",
        github_connected=True,
        github_username="kaushalkr585-cmd",
        github_token=encrypt_secret("ghp_valid_token_abc"),
    )
    db.add(user)
    db.flush()
    conv = ConversationRecord(id=str(uuid.uuid4()), user_id=user.id, title="GitHub Chat")
    db.add(conv)
    db.commit()

    # Fake LLM client supporting chat_with_tools + stream_chat
    class FakeLLM:
        def __init__(self) -> None:
            self.calls = 0

        def stream_chat(self, messages):
            yield "Hello! Doing great."

        def chat_with_tools(self, messages, tools=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "get_commit_history",
                            "arguments": {
                                "owner": "kaushalkr585-cmd",
                                "repo": "Nexarion-",
                                "limit": 2,
                            },
                        }
                    ],
                }
            return {
                "content": "Latest commit on `kaushalkr585-cmd/Nexarion-` (`main`) is `abc1234` fixing auth.",
                "tool_calls": [],
            }

    fake_llm = FakeLLM()
    orch = GitHubChatOrchestrator(
        db=db,
        user=user,
        conversation_id=conv.id,
        llm_client=fake_llm,
        base_system_prompt="You are Nexarion.",
    )

    # 1. Casual greeting skips GitHub API calls completely
    with patch.object(
        GitHubService, "list_repositories", side_effect=AssertionError("Should not call GitHub")
    ):
        casual_events = list(
            orch.run_stream(
                prompt="Hi, how are you?",
                history=[{"role": "user", "content": "Hi, how are you?"}],
            )
        )
        assert (
            "".join(e["chunk"] for e in casual_events if e["type"] == "token")
            == "Hello! Doing great."
        )

    # 2. GitHub prompt resolves repo, invokes tool calling, saves locked conversation context
    with (
        patch.object(
            GitHubService,
            "list_repositories",
            return_value=[
                {
                    "id": 101,
                    "name": "Nexarion-",
                    "full_name": "kaushalkr585-cmd/Nexarion-",
                    "owner": "kaushalkr585-cmd",
                    "private": False,
                    "default_branch": "main",
                }
            ],
        ),
        patch.object(
            GitHubService,
            "get_commit_history",
            return_value=[
                {
                    "sha": "abc1234567890",
                    "short_sha": "abc1234",
                    "message": "Fix JWT refresh",
                    "author": "kaushalkr585-cmd",
                    "date": "2026-11-25T10:00:00Z",
                    "html_url": "https://github.com/kaushalkr585-cmd/Nexarion-/commit/abc1234",
                }
            ],
        ),
    ):
        gh_events = list(
            orch.run_stream(
                prompt="Show my latest commits in Nexarion",
                history=[{"role": "user", "content": "Show my latest commits in Nexarion"}],
            )
        )
        stages = [e["stage"] for e in gh_events if e["type"] == "status"]
        assert "connecting" in stages
        assert "discovering" in stages
        assert "fetching" in stages
        output_text = "".join(e["chunk"] for e in gh_events if e["type"] == "token")
        assert "abc1234" in output_text

    # Verify conversation repository context was persisted for follow-up turns
    ctx = db.query(ConversationRepositoryContextRecord).filter_by(conversation_id=conv.id).first()
    assert ctx is not None
    assert ctx.repository_full_name == "kaushalkr585-cmd/Nexarion-"
    assert ctx.last_inspected_commit == "abc1234567890"


def test_conversation_repo_context_endpoint_ownership(
    client: TestClient, user_one: UserRecord, user_two: UserRecord
):
    db = next(get_db())
    conv = ConversationRecord(id=str(uuid.uuid4()), user_id=user_one.id, title="Owned Conv")
    db.add(conv)
    db.commit()

    u1_token = create_access_token({"sub": user_one.id, "email": user_one.email})
    u2_token = create_access_token({"sub": user_two.id, "email": user_two.email})

    with patch.object(
        GitHubService,
        "get_repository_details",
        return_value={
            "id": 999,
            "full_name": "kaushalkr585-cmd/Nexarion-",
            "default_branch": "main",
        },
    ):
        post_res = client.post(
            f"/api/github/context/{conv.id}",
            json={"repository_full_name": "kaushalkr585-cmd/Nexarion-"},
            headers={"Authorization": f"Bearer {u1_token}"},
        )
        assert post_res.status_code == 200
        assert post_res.json()["repository_full_name"] == "kaushalkr585-cmd/Nexarion-"

    # User 2 must get 404 (cannot access User 1's conversation repo context)
    u2_res = client.get(
        f"/api/github/context/{conv.id}",
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    assert u2_res.status_code == 404


def test_chat_stream_endpoint_github_mode_end_to_end(client: TestClient, user_one: UserRecord):
    token = create_access_token({"sub": user_one.id, "email": user_one.email})
    with patch("code_review.web.routes.conversation_routes.get_llm_client") as mock_factory:
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = True
        mock_llm.model = "mock-nemotron"
        mock_llm.stream_chat.return_value = iter(["Connect GitHub ", "ready."])
        mock_llm.chat_with_tools.return_value = {
            "content": "GitHub inspection complete.",
            "tool_calls": [],
        }
        mock_factory.return_value = mock_llm

        res = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Inspect my Nexarion project",
                "github_mode": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        body = res.text
        assert "event: init" in body
        assert "event: token" in body
        assert "event: done" in body
        assert "Connect GitHub" in body


def test_repo_disambiguation_ecommerce_vs_portfolio():
    from code_review.github.chat_orchestrator import _match_repositories_to_prompt

    repos = [
        {
            "id": 1,
            "name": "Modern-Portfolio-Website-HTML-REACT-TAILWIND-CSS",
            "full_name": "kaushalkr585-cmd/Modern-Portfolio-Website-HTML-REACT-TAILWIND-CSS",
            "default_branch": "main",
        },
        {
            "id": 2,
            "name": "Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
            "full_name": "kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
            "default_branch": "master",
        },
    ]

    # Test 1: User specifies Ecommerce repository
    match, ambiguous = _match_repositories_to_prompt(
        "Inspect my Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB repository",
        repos,
    )
    assert match is not None
    assert match["name"] == "Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB"
    assert match["id"] == 2
    assert not ambiguous

    # Test 2: User specifies Portfolio repository
    match2, ambiguous2 = _match_repositories_to_prompt(
        "Inspect my Modern-Portfolio-Website-HTML-REACT-TAILWIND-CSS project",
        repos,
    )
    assert match2 is not None
    assert match2["name"] == "Modern-Portfolio-Website-HTML-REACT-TAILWIND-CSS"
    assert match2["id"] == 1
    assert not ambiguous2

    # Test 3: Short keyword 'ecommerce'
    match3, _ = _match_repositories_to_prompt("analyze the ecommerce repo", repos)
    assert match3 is not None
    assert match3["id"] == 2

    # Test 4: Short keyword 'portfolio'
    match4, _ = _match_repositories_to_prompt("audit my portfolio site", repos)
    assert match4 is not None
    assert match4["id"] == 1


def test_is_raw_tool_leakage_detection():
    from code_review.github.chat_orchestrator import is_raw_tool_leakage

    # Raw tool dictionary
    raw_dict = '{"path": "frontend/src/App.js", "sha": "abc123", "size": 1290, "html_url": "https://github.com/...", "line_count": 50, "truncated": false, "content": "export default App;"}'
    assert is_raw_tool_leakage(raw_dict) is True

    # Raw JSON array of commit objects
    raw_commits = '[{"sha": "abc1234", "commit": {"message": "fix: auth"}}]'
    assert is_raw_tool_leakage(raw_commits) is True

    # Markdown code fence wrapping raw tool output
    fenced = '```json\n{"path": "server.js", "line_count": 100, "html_url": "https://github.com/test/server.js"}\n```'
    assert is_raw_tool_leakage(fenced) is True

    # Clean human markdown should NOT be flagged as raw leakage
    clean_markdown = "### Repository Overview\nHere is the analysis of your React application with components in `frontend/src`."
    assert is_raw_tool_leakage(clean_markdown) is False


def test_full_repo_inspection_pipeline_emits_structured_report(user_one: UserRecord):
    from code_review.github.chat_orchestrator import GitHubChatOrchestrator, is_raw_tool_leakage
    from code_review.github.service import GitHubService

    db = next(get_db())
    conv = ConversationRecord(id=str(uuid.uuid4()), user_id=user_one.id, title="Inspection Conv")
    db.add(conv)
    db.commit()

    conn = GitHubConnectionRecord(
        user_id=user_one.id,
        auth_method="pat",
        encrypted_access_token=encrypt_secret("ghp_test_token"),
        connection_status="connected",
        created_at=datetime.now(UTC),
    )
    db.add(conn)
    db.commit()

    mock_llm = MagicMock()
    mock_llm.stream_chat.return_value = iter(
        [
            "# Repository Inspection: kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB\n\n",
            "## A. Repository Overview\nFull stack e-commerce app.\n\n",
            "## B. Project Architecture\nFrontend React with Express backend.\n\n",
            "## C. Technology Stack\nReact, Node, Express, MongoDB.\n\n",
            "## D. Key Findings & Code Review\n1. Security: Clean.\n\n",
            "## E. Overall Assessment\nProduction ready.\n\n",
            "## F. Recommended Next Steps\nAdd integration tests.\n",
        ]
    )

    orch = GitHubChatOrchestrator(
        db=db,
        user=user_one,
        conversation_id=conv.id,
        llm_client=mock_llm,
        base_system_prompt="Base prompt",
    )

    with (
        patch.object(
            GitHubService,
            "list_repositories",
            return_value=[
                {
                    "id": 1,
                    "name": "Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
                    "full_name": "kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
                    "default_branch": "main",
                }
            ],
        ),
        patch.object(
            GitHubService,
            "get_repository_details",
            return_value={
                "id": 1,
                "full_name": "kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
                "default_branch": "main",
                "html_url": "https://github.com/kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB",
                "visibility": "public",
                "description": "MERN Stack E-Commerce",
            },
        ),
        patch.object(
            GitHubService,
            "get_commit_history",
            return_value=[{"sha": "def4567890", "message": "initial commit"}],
        ),
        patch.object(
            GitHubService,
            "get_repository_tree",
            return_value={
                "entries": [
                    {"path": "package.json", "type": "blob"},
                    {"path": "server.js", "type": "blob"},
                    {"path": "client/src/App.js", "type": "blob"},
                ]
            },
        ),
        patch.object(
            GitHubService,
            "fetch_file",
            return_value={
                "path": "package.json",
                "content": '{"dependencies": {"express": "^4.18.2"}}',
                "blocked": False,
            },
        ),
    ):
        events = list(
            orch.run_stream(
                prompt="Inspect my Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB repository",
                history=[],
            )
        )

        stages = [e.get("stage") for e in events if e.get("type") == "status"]
        assert "exploring" in stages
        assert "analyzing" in stages
        assert "finalizing" in stages

        meta_events = [e for e in events if e.get("type") == "meta"]
        assert len(meta_events) >= 1
        assert (
            meta_events[0]["repository"]
            == "kaushalkr585-cmd/Ecommerce-Website-HTML-CSS-JS-REACT-NODE-EXPRESS-MONGODB"
        )
        assert meta_events[0]["commit_sha"] == "def4567890"

        token_chunks = [e["chunk"] for e in events if e.get("type") == "token"]
        full_text = "".join(token_chunks)
        assert "## A. Repository Overview" in full_text
        assert "## B. Project Architecture" in full_text
        assert "## C. Technology Stack" in full_text
        assert "## D. Key Findings & Code Review" in full_text
        assert "## E. Overall Assessment" in full_text
        assert "## F. Recommended Next Steps" in full_text
        # Ensure zero raw JSON leakage
        assert not is_raw_tool_leakage(full_text)


def test_tool_registry_strict_validation_empty_path_unknown_tool_and_context_mismatch():
    import json

    from code_review.github.tools import GitHubToolRegistry

    mock_service = MagicMock()
    registry = GitHubToolRegistry(
        mock_service,
        default_owner="kaushalkr585-cmd",
        default_repo="Thumblify",
        default_ref="main",
    )

    # 1. Empty file path must be rejected before calling GitHubService
    empty_res = json.loads(
        registry.execute(
            "fetch_file", {"owner": "kaushalkr585-cmd", "repo": "Thumblify", "path": ""}
        )
    )
    assert empty_res["error_code"] == "INVALID_ARGUMENTS"
    assert "cannot be empty" in empty_res["error"]
    mock_service.fetch_file.assert_not_called()

    # 2. Unknown / unregistered hallucinated tool name
    unknown_res = json.loads(
        registry.execute(
            "github_get_file_content",
            {"owner": "kaushalkr585-cmd", "repo": "Thumblify", "path": "src/App.jsx"},
        )
    )
    assert unknown_res["error_code"] == "UNKNOWN_TOOL"
    assert "github_get_file_content" in unknown_res["error"]

    # 3. Malformed arguments flagged by LLM client parser
    malformed_res = json.loads(
        registry.execute(
            "fetch_file",
            {"_malformed_arguments": True, "_parse_error": "Expecting ',' delimiter"},
        )
    )
    assert malformed_res["error_code"] == "MALFORMED_ARGUMENTS"
    assert "delimiter" in malformed_res["error"]

    # 4. Cross-repository context mismatch blocked cleanly
    mismatch_res = json.loads(
        registry.execute(
            "fetch_file",
            {"owner": "kaushalkr585-cmd", "repo": "OtherRepo", "path": "package.json"},
        )
    )
    assert mismatch_res["error_code"] == "INVALID_ARGUMENTS"
    assert "Repository context mismatch" in mismatch_res["error"]
    mock_service.fetch_file.assert_not_called()


def test_nemotron_client_native_multi_tool_calls_and_malformed_args():
    import json

    from code_review.github.tools import GITHUB_TOOL_DEFINITIONS
    from code_review.llm.nemotron_client import NemotronClient

    client = NemotronClient(api_key="nvapi-test-key", model="nvidia/nemotron-3-ultra-550b-a55b")
    api_payload = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_repository_tree",
                                "arguments": json.dumps(
                                    {"owner": "kaushalkr585-cmd", "repo": "Thumblify"}
                                ),
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "fetch_file",
                                "arguments": '{"owner": "kaushalkr585-cmd", broken_json',
                            },
                        },
                    ],
                },
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(api_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        parsed = client.chat_with_tools(
            [{"role": "user", "content": "check security"}],
            tools=GITHUB_TOOL_DEFINITIONS,
        )

    assert len(parsed["tool_calls"]) == 2
    assert parsed["tool_calls"][0]["name"] == "get_repository_tree"
    assert parsed["tool_calls"][0]["arguments"]["repo"] == "Thumblify"
    assert parsed["tool_calls"][1]["name"] == "fetch_file"
    assert parsed["tool_calls"][1]["arguments"]["_malformed_arguments"] is True


def test_stream_tool_leakage_filter_blocks_partial_and_complete_tool_json():
    from code_review.github.chat_orchestrator import (
        _filter_stream_tool_leakage,
        is_raw_tool_leakage,
    )

    raw_leaked_line = '{"tool":"github_get_file_content","arguments":{"owner":"kaushalkr585-cmd","repo":"Thumbify","path":""}}\n'
    assert is_raw_tool_leakage(raw_leaked_line) is True

    stream_chunks = [
        "I found ",
        "two issues.\n",
        '{"tool":"github_get_',
        'file_content","arguments":{"owner":"kaushalkr585-cmd","repo":"Thumblify","path":""}}\n',
        "[Tool fetch_file result]:\n",
        '{"path": "server.ts"}\n',
        "1. Hardcoded CORS policy.\n",
    ]
    state: dict[str, bool] = {}
    filtered = "".join(_filter_stream_tool_leakage(iter(stream_chunks), state))
    assert "I found two issues." in filtered
    assert "1. Hardcoded CORS policy." in filtered
    assert "github_get_file_content" not in filtered
    assert '"tool"' not in filtered
    assert "[Tool" not in filtered
    assert state.get("leaked") is True


def test_fuzzy_repo_match_and_multi_language_security_scanner(user_one: UserRecord):
    from code_review.github.chat_orchestrator import _match_repositories_to_prompt
    from code_review.github.explorer import RepositoryExplorer

    repos = [
        {
            "id": 10,
            "name": "Thumblify",
            "full_name": "kaushalkr585-cmd/Thumblify",
            "default_branch": "main",
        },
        {
            "id": 11,
            "name": "ChatBot",
            "full_name": "kaushalkr585-cmd/ChatBot",
            "default_branch": "main",
        },
    ]
    matched, amb = _match_repositories_to_prompt(
        "Check the security issues in Thumbify repo", repos
    )
    assert matched is not None
    assert matched["full_name"] == "kaushalkr585-cmd/Thumblify"
    assert not amb

    mock_svc = MagicMock()
    mock_svc.fetch_file.side_effect = [
        {
            "path": "server/server.ts",
            "content": (
                "import express from 'express';\n"
                "import cors from 'cors';\n"
                "const app = express();\n"
                "app.use(cors({ origin: '*', credentials: true }));\n"
            ),
            "blocked": False,
        },
        {
            "path": "server/controllers/AuthControllers.ts",
            "content": (
                "export async function login(req, res) {\n"
                "  const secret = process.env.JWT_SECRET || 'devsecret123';\n"
                "  res.redirect(req.query.next);\n"
                "}\n"
            ),
            "blocked": False,
        },
    ]
    explorer = RepositoryExplorer(mock_svc)
    scan = explorer.run_agents_on_files(
        "kaushalkr585-cmd",
        "Thumblify",
        ["server/server.ts", "server/controllers/AuthControllers.ts"],
        ref="main",
        agent_ids=["security"],
    )
    assert scan["total_findings"] >= 4
    rule_ids = {f["rule_id"] for f in scan["findings"]}
    assert "SEC-JS005" in rule_ids  # hardcoded JWT fallback secret
    assert "SEC-JS006" in rule_ids  # wildcard CORS
    assert "SEC-JS009" in rule_ids  # open redirect
    assert "SEC-EXP001" in rule_ids  # missing helmet
    for f in scan["findings"]:
        assert f["file"]
        assert f["line"] >= 1
        assert f["evidence"]
        assert f["suggestion"]


def test_chat_orchestrator_native_tools_multi_step_and_synthesis_no_leak(user_one: UserRecord):
    from code_review.github.chat_orchestrator import GitHubChatOrchestrator, is_raw_tool_leakage
    from code_review.github.service import GitHubService

    db = next(get_db())
    conv = ConversationRecord(id=str(uuid.uuid4()), user_id=user_one.id, title="Thumblify Audit")
    db.add(conv)
    db.commit()

    conn = GitHubConnectionRecord(
        user_id=user_one.id,
        auth_method="pat",
        encrypted_access_token=encrypt_secret("ghp_test_token"),
        connection_status="connected",
        created_at=datetime.now(UTC),
    )
    db.add(conn)
    db.commit()

    mock_llm = MagicMock()
    # Round 0: native tool call for tree; Round 1: multiple parallel tool calls (batch fetch + security scan); Round 2: clean final answer
    mock_llm.chat_with_tools.side_effect = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_tree",
                    "name": "get_repository_tree",
                    "arguments": {"owner": "kaushalkr585-cmd", "repo": "Thumblify"},
                }
            ],
            "raw_tool_calls": [
                {
                    "id": "call_tree",
                    "type": "function",
                    "function": {
                        "name": "get_repository_tree",
                        "arguments": '{"owner":"kaushalkr585-cmd","repo":"Thumblify"}',
                    },
                }
            ],
        },
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_fetch",
                    "name": "fetch_files",
                    "arguments": {
                        "owner": "kaushalkr585-cmd",
                        "repo": "Thumblify",
                        "paths": ["server/server.ts"],
                    },
                },
                {
                    "id": "call_sec",
                    "name": "run_security_and_quality_agents",
                    "arguments": {
                        "owner": "kaushalkr585-cmd",
                        "repo": "Thumblify",
                        "paths": ["server/server.ts"],
                        "agents": ["security"],
                    },
                },
            ],
        },
        {
            "content": (
                "### Security Analysis for `kaushalkr585-cmd/Thumblify`\n\n"
                "- **WARNING (`SEC-JS006`)** in `server/server.ts:4`: Wildcard CORS origin configured."
            ),
            "tool_calls": [],
        },
    ]

    orch = GitHubChatOrchestrator(
        db=db,
        user=user_one,
        conversation_id=conv.id,
        llm_client=mock_llm,
        base_system_prompt="Base prompt",
    )

    with (
        patch.object(
            GitHubService,
            "list_repositories",
            return_value=[
                {
                    "id": 42,
                    "name": "Thumblify",
                    "full_name": "kaushalkr585-cmd/Thumblify",
                    "default_branch": "main",
                }
            ],
        ),
        patch.object(
            GitHubService,
            "get_repository_tree",
            return_value={
                "sha": "e5cfce3583ba5d42844f6ecafb1c407d1fb8cd84",
                "entries": [{"path": "server/server.ts", "type": "blob", "size": 120}],
            },
        ),
        patch.object(
            GitHubService,
            "fetch_file",
            return_value={
                "path": "server/server.ts",
                "html_url": "https://github.com/kaushalkr585-cmd/Thumblify/blob/main/server/server.ts",
                "line_count": 4,
                "truncated": False,
                "content": "const app = express();\napp.use(cors({ origin: '*', credentials: true }));",
                "blocked": False,
            },
        ),
    ):
        events = list(
            orch.run_stream(
                prompt="Check the security issues in Thumbify repo",
                history=[
                    {"role": "user", "content": "Check the security issues in Thumbify repo"}
                ],
            )
        )

    assert mock_llm.chat_with_tools.call_count == 3
    output_text = "".join(e["chunk"] for e in events if e.get("type") == "token")
    assert "SEC-JS006" in output_text
    assert "server/server.ts" in output_text
    assert not is_raw_tool_leakage(output_text)
    assert "github_get_file_content" not in output_text
