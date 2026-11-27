from __future__ import annotations

import json
from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_review.analysis.conversation_memory import ConversationMemoryManager
from code_review.analysis.embedding_service import DEFAULT_NVIDIA_EMBED_MODEL, EmbeddingService
from code_review.db.database import get_db
from code_review.db.models import Base, ConversationRecord
from code_review.github.chat_orchestrator import GitHubChatOrchestrator
from code_review.github.mode_router import ToolExecutionRouter, UserIntent
from code_review.llm.nemotron_client import (
    DEFAULT_NVIDIA_MODEL,
    NemotronClient,
    NemotronResponseError,
    reset_model_cooldowns,
)
from code_review.web.app import create_app
from code_review.web.routes import conversation_routes


def _parse_sse(raw_text: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in raw_text.replace("\r\n", "\n").split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        if not lines:
            continue
        evt_name = "message"
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("event:"):
                evt_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        payload_str = "\n".join(data_lines)
        try:
            payload = json.loads(payload_str)
        except Exception:
            payload = payload_str
        events.append((evt_name, payload))
    return events


@pytest.fixture()
def isolated_api_client(tmp_path):
    db_path = tmp_path / "reliability_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    app = create_app()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(conversation_routes, "get_session_factory", return_value=session_local)
        )
        stack.enter_context(
            patch("code_review.db.database.get_session_factory", return_value=session_local)
        )
        with TestClient(app) as client:
            yield client, session_local


def test_normal_mode_uses_direct_pipeline_without_github_or_is_available_probe(
    isolated_api_client,
):
    client, _ = isolated_api_client

    called_thinking_flags: list[bool] = []
    called_is_available = False

    class FakeAsyncNemotron(NemotronClient):
        def is_available(self) -> bool:
            nonlocal called_is_available
            called_is_available = True
            return True

        async def astream_chat(
            self,
            messages,
            *,
            temperature=None,
            max_tokens=4096,
            enable_thinking=True,
            ttft_timeout=15.0,
            idle_timeout=25.0,
        ):
            called_thinking_flags.append(enable_thinking)
            yield "Python is "
            yield "a versatile language."

    fake_client = FakeAsyncNemotron(api_key="nvapi-test-key", model=DEFAULT_NVIDIA_MODEL)

    with (
        patch.object(conversation_routes, "get_llm_client", return_value=fake_client),
        patch.object(
            GitHubChatOrchestrator,
            "run_stream",
            side_effect=AssertionError("GitHub orchestrator must not run in Normal mode!"),
        ),
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "What is Python?",
                "mode": "normal",
                "provider": "nvidia",
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)

    evt_names = [e[0] for e in events]
    assert "init" in evt_names
    assert "token" in evt_names
    assert "done" in evt_names
    assert not called_is_available, "Real NemotronClient stream should skip synchronous /models probe"
    assert called_thinking_flags == [False], "Simple normal Q&A should disable heavy thinking overhead"
    done_evt = next(p for name, p in events if name == "done")
    assert done_evt["content"] == "Python is a versatile language."
    assert done_evt["metrics"]["chunks"] == 2


def test_thinking_enabled_for_provided_code_blocks():
    plan = ToolExecutionRouter.plan_chat_request(
        prompt="Find bugs in:\n```python\ndef foo(x):\n    return 1 / 0\n```",
        requested_mode="normal",
    )
    assert plan.intent == UserIntent.ANALYZE_PROVIDED_CODE
    assert conversation_routes._should_enable_thinking(
        route_plan=plan,
        prompt="Find bugs in:\n```python\ndef foo(x):\n    return 1 / 0\n```",
        diff_context=None,
        document_context=None,
    )


def test_nemotron_client_fallback_on_timeout_and_fail_fast_on_401():
    reset_model_cooldowns()
    attempted_models: list[str] = []

    def timeout_then_ok_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        attempted_models.append(body["model"])
        if len(attempted_models) == 1:
            raise httpx.ReadTimeout("simulated slow primary model", request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Fallback answer"}}]},
            request=request,
        )

    mock_http = httpx.Client(transport=httpx.MockTransport(timeout_then_ok_handler))
    nc = NemotronClient(
        api_key="nvapi-test-key",
        model="nvidia/nemotron-3-ultra-550b-a55b",
        timeout=5.0,
    )

    with (
        patch("code_review.llm.nemotron_client.is_urlopen_patched", return_value=False),
        patch("code_review.llm.nemotron_client.get_shared_sync_http_client", return_value=mock_http),
    ):
        reply = nc.chat([{"role": "user", "content": "Hi"}], json_format=False)

    assert reply == "Fallback answer"
    assert len(attempted_models) == 2
    assert nc.last_call_meta["fallback_used"] is True
    assert nc.last_call_meta["retries"] >= 1

    # Verify 401 fails fast without wasteful model fallback
    auth_calls = 0

    def unauthorized_handler(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls
        auth_calls += 1
        return httpx.Response(401, json={"detail": "Invalid API key"}, request=request)

    mock_unauth_http = httpx.Client(transport=httpx.MockTransport(unauthorized_handler))
    with (
        patch("code_review.llm.nemotron_client.is_urlopen_patched", return_value=False),
        patch(
            "code_review.llm.nemotron_client.get_shared_sync_http_client",
            return_value=mock_unauth_http,
        ),
    ):
        with pytest.raises(NemotronResponseError):
            nc.chat([{"role": "user", "content": "Hi"}], json_format=False)
    assert auth_calls == 1


def test_simulated_provider_failures_emit_safe_sse_error_and_preserve_partial_text(
    isolated_api_client,
):
    client, session_local = isolated_api_client

    # Case 1: Missing NVIDIA API key -> safe sanitized error event
    empty_key_client = NemotronClient(api_key="", model=DEFAULT_NVIDIA_MODEL)
    with patch.object(conversation_routes, "get_llm_client", return_value=empty_key_client):
        resp = client.post(
            "/api/conversations/stream",
            json={"initial_message": "Hi.", "mode": "normal", "provider": "nvidia"},
        )
    events = _parse_sse(resp.text)
    err = next((p for n, p in events if n == "error"), None)
    assert err is not None
    assert "nvapi-" not in json.dumps(err)

    # Case 2: Mid-stream timeout after partial chunk preserves partial content + emits TIMEOUT error
    mock_client = MagicMock()
    mock_client.model = "mock-model"
    mock_client.is_available.return_value = True

    def failing_stream(_payload):
        yield "Partial response before drop. "
        raise TimeoutError("Read timed out after 15s")

    mock_client.stream_chat.side_effect = failing_stream

    with patch.object(conversation_routes, "get_llm_client", return_value=mock_client):
        resp2 = client.post(
            "/api/conversations/stream",
            json={"initial_message": "Explain API", "mode": "normal", "provider": "nvidia"},
        )
    events2 = _parse_sse(resp2.text)
    init_evt = next(p for n, p in events2 if n == "init")
    err_evt = next(p for n, p in events2 if n == "error")
    assert err_evt["error_code"] == "TIMEOUT"
    assert "couldn't get a response in time" in err_evt["user_message"]

    with session_local() as db:
        conv = db.query(ConversationRecord).filter_by(id=init_evt["id"]).first()
        assert conv is not None
        asst_msgs = [m for m in conv.messages if m.role == "assistant"]
        assert len(asst_msgs) == 1
        assert "Partial response before drop." in asst_msgs[0].content


def test_per_conversation_stream_registry_supersedes_same_conv_only():
    t1 = "trace-1"
    t2 = "trace-2"
    t3 = "trace-3"
    assert conversation_routes._register_active_stream("conv-alpha", t1) is None
    assert conversation_routes._is_active_stream("conv-alpha", t1) is True

    # Different conversation runs concurrently without interference
    assert conversation_routes._register_active_stream("conv-beta", t3) is None
    assert conversation_routes._is_active_stream("conv-alpha", t1) is True
    assert conversation_routes._is_active_stream("conv-beta", t3) is True

    # Newer request on same conversation supersedes older stream cleanly
    assert conversation_routes._register_active_stream("conv-alpha", t2) == t1
    assert conversation_routes._is_active_stream("conv-alpha", t1) is False
    assert conversation_routes._is_active_stream("conv-alpha", t2) is True

    # Clearing stale trace does not wipe newer active trace
    conversation_routes._clear_active_stream("conv-alpha", t1)
    assert conversation_routes._is_active_stream("conv-alpha", t2) is True
    conversation_routes._clear_active_stream("conv-alpha", t2)
    conversation_routes._clear_active_stream("conv-beta", t3)


def test_health_and_performance_endpoints(isolated_api_client):
    client, _ = isolated_api_client
    for _ in range(3):
        h = client.get("/health")
        ah = client.get("/api/health")
        mp = client.get("/api/metrics/performance")
        assert h.status_code == 200
        assert ah.status_code == 200
        assert mp.status_code == 200

        body = ah.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        perf = body["performance"]
        for key in (
            "total_requests",
            "avg_response_ms",
            "median_response_ms",
            "p95_response_ms",
            "avg_ttft_ms",
            "provider_failure_rate",
            "timeout_rate",
            "sse_disconnect_rate",
            "requests_by_provider_model",
        ):
            assert key in perf


def test_embedding_defaults_and_empty_memory_skips_network_call(isolated_api_client):
    _, session_local = isolated_api_client
    assert DEFAULT_NVIDIA_EMBED_MODEL == "nvidia/nemotron-3.5-embed-1b"

    with session_local() as db:
        with patch.object(
            EmbeddingService,
            "get_embedding",
            side_effect=AssertionError("Must not call embedding API when no stored memories exist!"),
        ):
            excerpts = ConversationMemoryManager.retrieve_relevant_memories(
                db=db,
                query="How does FastAPI dependency injection work?",
                user_id=None,
                current_conversation_id="conv-none",
            )
    assert excerpts == []


def test_performance_monitor_statistics_and_isolation():
    from code_review.observability import PerformanceMonitor, RequestPerformanceRecord

    mon = PerformanceMonitor(max_records=10)
    mon.record(
        RequestPerformanceRecord(
            request_id="r1",
            mode="normal",
            intent="casual_chat",
            provider="nvidia",
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            status_code=200,
            termination_reason="completed",
            total_ms=1000.0,
            ttft_ms=500.0,
            generation_ms=900.0,
            token_chunks=10,
        )
    )
    mon.record(
        RequestPerformanceRecord(
            request_id="r2",
            mode="normal",
            intent="general_coding",
            provider="nvidia",
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            status_code=504,
            termination_reason="timeout",
            total_ms=15000.0,
            retries=1,
            fallback_used=True,
            fallback_model="nvidia/nemotron-3.5-lightning-30b-a3b",
            error_code="TIMEOUT",
        )
    )
    mon.record(
        RequestPerformanceRecord(
            request_id="r3",
            mode="normal",
            intent="casual_chat",
            provider="nvidia",
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            status_code=499,
            termination_reason="disconnected",
            total_ms=2000.0,
            ttft_ms=600.0,
            generation_ms=1900.0,
            error_code="CLIENT_DISCONNECTED",
        )
    )

    snap = mon.snapshot()
    assert snap["total_requests"] == 3
    assert snap["median_response_ms"] == 2000.0
    assert snap["avg_ttft_ms"] == 550.0
    assert snap["total_retries"] == 1
    assert snap["timeout_rate"] == round(1 / 3, 4)
    assert snap["provider_failure_rate"] == round(1 / 3, 4)
    assert snap["sse_disconnect_rate"] == round(1 / 3, 4)
    pm_bucket = snap["requests_by_provider_model"]["nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"]
    assert pm_bucket["requests"] == 3
    assert pm_bucket["timeouts"] == 1
    assert pm_bucket["fallbacks"] == 1


def test_nemotron_model_cooldown_reorders_stalled_primary_and_resets():
    from code_review.llm.nemotron_client import _mark_model_unhealthy

    reset_model_cooldowns()
    nc = NemotronClient(api_key="nvapi-test-key", model="nvidia/nemotron-3-ultra-550b-a55b")
    assert nc._candidate_models()[0] == "nvidia/nemotron-3-ultra-550b-a55b"

    _mark_model_unhealthy("nvidia/nemotron-3-ultra-550b-a55b", cooldown=60.0)
    reordered = nc._candidate_models()
    assert reordered[0] == DEFAULT_NVIDIA_MODEL
    assert reordered[-1] == "nvidia/nemotron-3-ultra-550b-a55b"

    reset_model_cooldowns()
    assert nc._candidate_models()[0] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_github_orchestrator_stream_runs_async_and_completes_without_timeout(isolated_api_client):
    client, _ = isolated_api_client

    class FakeSlowGitHubOrch:
        def __init__(self, *args, **kwargs):
            pass

        def run_stream(self, *, prompt: str, history, explicit_repo=None):
            yield {"type": "status", "stage": "connecting", "detail": "Connecting to GitHub..."}
            yield {
                "type": "meta",
                "repository": "owner/Vortx",
                "branch": "main",
                "commit_sha": "022c049",
            }
            yield {"type": "token", "chunk": "# Repository Inspection: owner/Vortx\n\nComplete."}

    mock_llm = MagicMock()
    mock_llm.model = DEFAULT_NVIDIA_MODEL
    mock_llm.is_available.return_value = True

    with (
        patch.object(conversation_routes, "get_llm_client", return_value=mock_llm),
        patch.object(conversation_routes, "GitHubChatOrchestrator", FakeSlowGitHubOrch),
    ):
        resp = client.post(
            "/api/conversations/stream",
            json={
                "initial_message": "inspect my vortx repository",
                "mode": "github",
                "github_mode": True,
                "provider": "nvidia",
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)

    evt_names = [n for n, _ in events]
    assert "repo_meta" in evt_names
    assert "token" in evt_names
    assert "done" in evt_names
    done_evt = next(p for n, p in events if n == "done")
    assert "Repository Inspection: owner/Vortx" in done_evt["content"]


