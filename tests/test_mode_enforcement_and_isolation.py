"""Comprehensive backend tests for strict Normal/GitHub chat mode enforcement and isolation."""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from code_review.db.database import get_db, init_database
from code_review.db.models import (
    ConversationRecord,
    ConversationRepositoryContextRecord,
    MessageRecord,
    UserRecord,
)
from code_review.github.mode_router import (
    PR_SCOPED_TOOLS,
    REPO_INSPECTION_SCOPED_TOOLS,
    REPO_LIST_SCOPED_TOOLS,
    ChatModeResolver,
    IntentClassifier,
    ProgressMessageManager,
    ToolExecutionRouter,
    UserIntent,
)
from code_review.github.tools import GitHubToolRegistry
from code_review.web.app import app
from code_review.web.auth import create_access_token
from code_review.web.schemas import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    MessageCreateRequest,
    MessageEditRequest,
    MessageRegenerateRequest,
)


FORBIDDEN_NORMAL_STATUS_SNIPPETS = (
    "planning github",
    "connecting to github",
    "discovering repositories",
    "inspecting repository",
)


def _parse_sse_events(raw_text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw_text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        raw_json = "\n".join(data_lines)
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = {"raw": raw_json}
        events.append((event_name, payload))
    return events


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    init_database()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@contextlib.contextmanager
def _managed_db():
    gen = get_db()
    db = next(gen)
    try:
        yield db
    finally:
        gen.close()


@pytest.fixture
def normal_user() -> Generator[UserRecord, None, None]:
    with _managed_db() as db:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=f"mode_normal_{uuid.uuid4().hex[:8]}@nexarion.dev",
            name="Mode Normal User",
            github_connected=False,
            github_token=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user


@pytest.fixture
def connected_user() -> Generator[UserRecord, None, None]:
    with _managed_db() as db:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=f"mode_gh_{uuid.uuid4().hex[:8]}@nexarion.dev",
            name="Mode GitHub Connected User",
            github_connected=True,
            github_username="nexarion-dev",
            github_token="ghp_test_token_1234567890",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user


def _auth_headers(user: UserRecord) -> dict[str, str]:
    token = create_access_token({"sub": user.id, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _make_mock_llm(reply_text: str = "Normal assistant reply.") -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.chat.return_value = reply_text

    def _stream_chat(messages: list[dict[str, Any]]) -> Generator[str, None, None]:
        yield reply_text

    mock_llm.stream_chat.side_effect = _stream_chat
    mock_llm.supports_native_tools.return_value = False
    return mock_llm


# ---------------------------------------------------------------------------
# 1. Schema & Mode Validation Tests
# ---------------------------------------------------------------------------


def test_request_schemas_accept_valid_modes_and_reject_invalid_modes():
    for valid_mode in ("normal", "github"):
        assert ConversationCreateRequest(mode=valid_mode).mode == valid_mode
        assert ConversationUpdateRequest(mode=valid_mode).mode == valid_mode
        assert MessageCreateRequest(content="hello", mode=valid_mode).mode == valid_mode
        assert MessageRegenerateRequest(mode=valid_mode).mode == valid_mode
        assert MessageEditRequest(content="edited", mode=valid_mode).mode == valid_mode

    for bad_mode in ("invalid", "", "auto", 123, "GITHUB_MODE"):
        with pytest.raises(ValidationError):
            MessageCreateRequest(content="hello", mode=bad_mode)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            ConversationCreateRequest(mode=bad_mode)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            ConversationUpdateRequest(mode=bad_mode)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            MessageRegenerateRequest(mode=bad_mode)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            MessageEditRequest(content="edited", mode=bad_mode)  # type: ignore[arg-type]


def test_mode_resolver_never_defaults_to_github_and_explicit_mode_wins():
    assert ChatModeResolver.resolve() == "normal"
    assert ChatModeResolver.resolve(mode=None, github_mode=None) == "normal"
    assert ChatModeResolver.resolve(mode=None, github_mode=False) == "normal"
    assert ChatModeResolver.resolve(mode=None, github_mode=True) == "github"
    # Explicit mode="normal" strictly overrides stale legacy github_mode=True
    assert ChatModeResolver.resolve(mode="normal", github_mode=True) == "normal"
    assert ChatModeResolver.resolve(mode="github", github_mode=False) == "github"


def test_api_endpoints_reject_invalid_mode_with_422(client: TestClient, normal_user: UserRecord):
    headers = _auth_headers(normal_user)

    create_resp = client.post(
        "/api/conversations",
        json={"title": "Bad mode", "mode": "hacker_mode"},
        headers=headers,
    )
    assert create_resp.status_code == 422

    stream_create_resp = client.post(
        "/api/conversations/stream",
        json={"initial_message": "Hi", "mode": "invalid"},
        headers=headers,
    )
    assert stream_create_resp.status_code == 422

    # Create valid Normal conversation to test message/regenerate/edit/patch validation
    valid_conv_resp = client.post(
        "/api/conversations",
        json={"title": "Valid Conv", "mode": "normal"},
        headers=headers,
    )
    assert valid_conv_resp.status_code in (200, 201)
    conv_id = valid_conv_resp.json()["id"]

    assert (
        client.patch(
            f"/api/conversations/{conv_id}",
            json={"mode": "invalid"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "hello", "mode": "invalid"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={"content": "hello", "mode": 123},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/conversations/{conv_id}/regenerate/stream",
            json={"mode": "invalid"},
            headers=headers,
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# 2. Intent Classification & Tool Guard Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("Write a Python application for binary search", UserIntent.GENERAL_CODING),
        ("Debug this Python traceback in my function", UserIntent.ANALYZE_PROVIDED_CODE),
        ("Explain GitHub OAuth", UserIntent.EDUCATIONAL_GITHUB),
        ("Explain GitHub Actions", UserIntent.EDUCATIONAL_GITHUB),
        ("What is a pull request?", UserIntent.EDUCATIONAL_GITHUB),
        (
            "Review this pasted Python code:\n```python\n# Inspect my repository\ndef add(a, b):\n    return a + b\n```",
            UserIntent.ANALYZE_PROVIDED_CODE,
        ),
    ],
)
def test_non_github_and_educational_prompts_never_enable_github_tools(
    connected_user: UserRecord, prompt: str, expected_intent: UserIntent
):
    with _managed_db() as db:
        for mode in ("normal", "github"):
            plan = ToolExecutionRouter.plan_chat_request(
                prompt=prompt,
                requested_mode=mode,
                db=db,
                user=connected_user,
                has_locked_repo=True,
            )
            assert plan.intent == expected_intent
            assert plan.use_github_orchestrator is False
            assert plan.allow_github_tools is False
            assert plan.allowed_tools == frozenset()
            assert plan.persist_repo_context is False
            detail_lower = plan.initial_status["detail"].lower()
            for forbidden in FORBIDDEN_NORMAL_STATUS_SNIPPETS:
                assert forbidden not in detail_lower


def test_normal_mode_explicit_github_intent_requires_auth_and_uses_scoped_tools(
    normal_user: UserRecord, connected_user: UserRecord
):
    with _managed_db() as db:
        # Without GitHub authentication connected -> tools strictly denied
        unauth_plan = ToolExecutionRouter.plan_chat_request(
            prompt="Inspect my GitHub repository for issues",
            requested_mode="normal",
            db=db,
            user=normal_user,
        )
        assert unauth_plan.mode == "normal"
        assert unauth_plan.intent == UserIntent.GITHUB_REPO_INSPECTION
        assert unauth_plan.guard.auth_verified is False
        assert unauth_plan.allow_github_tools is False
        assert unauth_plan.allowed_tools == frozenset()
        assert unauth_plan.persist_repo_context is False

        # With connected user -> allowed strictly via narrow PR/repo scope, NEVER persists repo context
        pr_plan = ToolExecutionRouter.plan_chat_request(
            prompt="Analyze my latest pull request",
            requested_mode="normal",
            db=db,
            user=connected_user,
        )
        assert pr_plan.mode == "normal"
        assert pr_plan.intent == UserIntent.GITHUB_PR_OPERATION
        assert pr_plan.guard.auth_verified is True
        assert pr_plan.allow_github_tools is True
        assert pr_plan.allowed_tools == PR_SCOPED_TOOLS
        assert "run_security_and_quality_agents" not in pr_plan.allowed_tools
        assert pr_plan.persist_repo_context is False

        repo_plan = ToolExecutionRouter.plan_chat_request(
            prompt="Inspect my GitHub repository",
            requested_mode="normal",
            db=db,
            user=connected_user,
        )
        assert repo_plan.mode == "normal"
        assert repo_plan.intent == UserIntent.GITHUB_REPO_INSPECTION
        assert repo_plan.allowed_tools == REPO_INSPECTION_SCOPED_TOOLS
        assert "get_pull_request_diff" not in repo_plan.allowed_tools
        assert repo_plan.persist_repo_context is False

        list_plan = ToolExecutionRouter.plan_chat_request(
            prompt="List my GitHub repositories",
            requested_mode="normal",
            db=db,
            user=connected_user,
        )
        assert list_plan.intent == UserIntent.GITHUB_REPO_LIST
        assert list_plan.allowed_tools == REPO_LIST_SCOPED_TOOLS
        assert list_plan.persist_repo_context is False


# ---------------------------------------------------------------------------
# 3. Direct GitHubToolRegistry Server-Side Enforcement Tests
# ---------------------------------------------------------------------------


def test_tool_registry_blocks_disallowed_tools_before_dispatch():
    mock_service = MagicMock()

    empty_registry = GitHubToolRegistry(mock_service, allowed_tools=frozenset())
    blocked_result = json.loads(empty_registry.execute("get_user_repositories", {}))
    assert blocked_result["error_code"] == "TOOL_BLOCKED"
    mock_service.get_user_repositories.assert_not_called()

    pr_only_registry = GitHubToolRegistry(mock_service, allowed_tools=PR_SCOPED_TOOLS)
    blocked_explore = json.loads(
        pr_only_registry.execute("explore_repository_overview", {"repo": "org/repo"})
    )
    assert blocked_explore["error_code"] == "TOOL_BLOCKED"
    mock_service.explore_repository_overview.assert_not_called()

    mock_service.list_pull_requests.return_value = [{"number": 12, "title": "Fix bug"}]
    pr_only_registry.execute("get_pull_requests", {"repo": "org/repo"})
    mock_service.list_pull_requests.assert_called_once()


# ---------------------------------------------------------------------------
# 4. End-to-End FastAPI Route & SSE Normal Mode Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "Write a Python script for quicksort",
        "Explain GitHub OAuth",
        "Explain GitHub Actions",
        "What is a pull request?",
        "Review this pasted Python code:\n```python\ndef foo(x):\n    return x * 2\n```",
    ],
)
def test_normal_mode_sse_never_invokes_github_or_emits_github_status(
    client: TestClient, connected_user: UserRecord, prompt: str
):
    headers = _auth_headers(connected_user)
    mock_llm = _make_mock_llm("Clear normal coding answer.")

    with (
        patch(
            "code_review.web.routes.conversation_routes.get_llm_client",
            return_value=mock_llm,
        ),
        patch("code_review.github.chat_orchestrator.GitHubService") as mock_gh_service,
        patch(
            "code_review.web.routes.conversation_routes.GitHubChatOrchestrator"
        ) as mock_gh_orch,
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={"initial_message": prompt, "mode": "normal"},
            headers=headers,
        )
        assert resp.status_code == 200
        mock_gh_service.assert_not_called()
        mock_gh_orch.assert_not_called()

    events = _parse_sse_events(resp.text)
    event_names = [name for name, _ in events]
    assert "init" in event_names
    assert "done" in event_names

    init_payload = next(payload for name, payload in events if name == "init")
    done_payload = next(payload for name, payload in events if name == "done")
    assert init_payload["mode"] == "normal"
    assert done_payload["mode"] == "normal"

    status_details = [
        str(payload.get("detail", "")).lower()
        for name, payload in events
        if name == "status"
    ]
    for detail in status_details:
        for forbidden in FORBIDDEN_NORMAL_STATUS_SNIPPETS:
            assert forbidden not in detail


def test_normal_mode_blocks_github_even_if_repo_context_exists_and_mode_switched(
    client: TestClient, connected_user: UserRecord
):
    headers = _auth_headers(connected_user)

    with _managed_db() as db:
        # Seed Conversation A originally created in GitHub Mode WITH a persisted repo context
        conv_github = ConversationRecord(
            id=str(uuid.uuid4()),
            user_id=connected_user.id,
            title="GitHub Conversation",
            mode="github",
        )
        db.add(conv_github)
        db.commit()
        conv_id = conv_github.id
        db.add(
            ConversationRepositoryContextRecord(
                conversation_id=conv_id,
                user_id=connected_user.id,
                repository_full_name="nexarion/backend",
                default_branch="main",
                selected_branch="main",
            )
        )
        db.commit()

    # Switch Conversation A explicitly to Normal Mode via PATCH
    patch_resp = client.patch(
        f"/api/conversations/{conv_id}",
        json={"mode": "normal"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["mode"] == "normal"

    mock_llm = _make_mock_llm("GitHub OAuth allows third-party apps to authenticate.")
    with (
        patch(
            "code_review.web.routes.conversation_routes.get_llm_client",
            return_value=mock_llm,
        ),
        patch("code_review.github.chat_orchestrator.GitHubService") as mock_gh_service,
        patch(
            "code_review.web.routes.conversation_routes.GitHubChatOrchestrator"
        ) as mock_gh_orch,
    ):
        # Even if client passes stale github_mode=True alongside mode="normal", Normal Mode wins!
        msg_stream = client.post(
            f"/api/conversations/{conv_id}/messages/stream",
            json={
                "content": "Explain GitHub OAuth",
                "mode": "normal",
                "github_mode": True,
            },
            headers=headers,
        )
        assert msg_stream.status_code == 200
        mock_gh_service.assert_not_called()
        mock_gh_orch.assert_not_called()

        # Non-streaming endpoint must also enforce Normal Mode
        non_stream_resp = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "content": "How do Python decorators work?",
                "mode": "normal",
            },
            headers=headers,
        )
        assert non_stream_resp.status_code == 200
        mock_gh_service.assert_not_called()
        mock_gh_orch.assert_not_called()

        # Regenerate and Edit streams in Normal Mode must also stay strictly in Normal Mode
        regen_resp = client.post(
            f"/api/conversations/{conv_id}/regenerate/stream",
            json={"mode": "normal"},
            headers=headers,
        )
        assert regen_resp.status_code == 200
        mock_gh_service.assert_not_called()
        mock_gh_orch.assert_not_called()

        # Find first user message to edit
        detail = client.get(f"/api/conversations/{conv_id}", headers=headers).json()
        user_msg_id = next(m["id"] for m in detail["messages"] if m["role"] == "user")
        edit_resp = client.post(
            f"/api/conversations/{conv_id}/messages/{user_msg_id}/edit/stream",
            json={"content": "Explain GitHub Actions", "mode": "normal"},
            headers=headers,
        )
        assert edit_resp.status_code == 200
        mock_gh_service.assert_not_called()
        mock_gh_orch.assert_not_called()

    # Check SSE events across all streaming responses contained zero forbidden GitHub statuses
    for raw_sse in (msg_stream.text, regen_resp.text, edit_resp.text):
        for name, payload in _parse_sse_events(raw_sse):
            if name == "status":
                detail = str(payload.get("detail", "")).lower()
                for forbidden in FORBIDDEN_NORMAL_STATUS_SNIPPETS:
                    assert forbidden not in detail

    # Creating a separate New Conversation B defaults to "normal" even while user has Conversation A
    conv_b_resp = client.post(
        "/api/conversations",
        json={"title": "Fresh Normal Chat"},
        headers=headers,
    )
    assert conv_b_resp.status_code in (200, 201)
    assert conv_b_resp.json()["mode"] == "normal"


def test_normal_mode_explicit_github_request_unauthenticated_and_authenticated(
    client: TestClient, normal_user: UserRecord, connected_user: UserRecord
):
    # 1. Unauthenticated user asking to inspect GitHub repo in Normal Mode -> zero GitHubService calls
    mock_llm_unauth = _make_mock_llm()
    with (
        patch(
            "code_review.web.routes.conversation_routes.get_llm_client",
            return_value=mock_llm_unauth,
        ),
        patch("code_review.github.chat_orchestrator.GitHubService") as mock_gh_service,
    ):
        resp_unauth = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "Inspect my GitHub repository",
                "mode": "normal",
            },
            headers=_auth_headers(normal_user),
        )
        assert resp_unauth.status_code == 200
        mock_gh_service.assert_not_called()

    events_unauth = _parse_sse_events(resp_unauth.text)
    done_unauth = next(p for n, p in events_unauth if n == "done")
    assert done_unauth["mode"] == "normal"
    assert "github" in done_unauth["content"].lower()
    for n, p in events_unauth:
        if n == "status":
            assert "planning github" not in str(p.get("detail", "")).lower()

    # 2. Connected user explicitly asking "Analyze my latest pull request" in Normal Mode:
    # runs strictly with PR_SCOPED_TOOLS and MUST NOT convert conversation mode or save repo lock.
    mock_llm_conn = _make_mock_llm("PR summary answer.")
    mock_llm_conn.chat_with_tools.return_value = MagicMock(
        content="No open pull requests found.",
        tool_calls=[],
    )
    captured_orchestrator_kwargs: dict[str, Any] = {}

    class _MockGHService:
        def __init__(self, token: str, cache_scope: str = "") -> None:
            self.token = token

        def get_authenticated_user(self) -> dict[str, Any]:
            return {"login": "nexarion-dev"}

        def get_user_repositories(self, **kwargs: Any) -> list[dict[str, Any]]:
            return [{"full_name": "nexarion-dev/demo", "default_branch": "main", "id": 1}]

    with (
        patch(
            "code_review.web.routes.conversation_routes.get_llm_client",
            return_value=mock_llm_conn,
        ),
        patch("code_review.github.chat_orchestrator.GitHubService", side_effect=_MockGHService),
    ):
        # Spy on allowed_tools passed to GitHubToolRegistry while keeping real enforcement
        orig_registry_init = GitHubToolRegistry.__init__

        def _spy_registry_init(self, service, **kwargs):
            captured_orchestrator_kwargs["allowed_tools"] = kwargs.get("allowed_tools")
            return orig_registry_init(self, service, **kwargs)

        with patch.object(GitHubToolRegistry, "__init__", _spy_registry_init):
            resp_conn = client.post(
                "/api/conversations/stream",
                json={
                    "initial_message": "Analyze my latest pull request",
                    "mode": "normal",
                },
                headers=_auth_headers(connected_user),
            )
            assert resp_conn.status_code == 200

    events_conn = _parse_sse_events(resp_conn.text)
    init_conn = next(p for n, p in events_conn if n == "init")
    conv_id = init_conn["id"]
    assert init_conn["mode"] == "normal"

    # Verify DB conversation remained "normal" and NO repo lock was persisted
    with _managed_db() as db:
        conv_row = db.query(ConversationRecord).filter(ConversationRecord.id == conv_id).first()
        assert conv_row is not None
        assert conv_row.mode == "normal"

        repo_lock = (
            db.query(ConversationRepositoryContextRecord)
            .filter(ConversationRepositoryContextRecord.conversation_id == conv_id)
            .first()
        )
        assert repo_lock is None

    if "allowed_tools" in captured_orchestrator_kwargs:
        assert captured_orchestrator_kwargs["allowed_tools"] == PR_SCOPED_TOOLS
