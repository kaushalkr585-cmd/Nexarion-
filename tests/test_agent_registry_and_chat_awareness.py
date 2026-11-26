from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from code_review.agents.registry import (
    DEFAULT_AGENT_DEFINITIONS,
    ensure_default_agents_seeded,
    get_agent_registry_summary,
    get_registered_agents,
)
from code_review.db.database import get_db
from code_review.db.init_db import DEFAULT_AGENTS
from code_review.db.models import AgentConfigRecord
from code_review.orchestrator import ReviewOrchestrator
from code_review.web.app import app
from code_review.web.routes.conversation_routes import (
    _build_system_prompt,
    _is_explicit_model_query,
)


def test_single_source_of_truth_seven_agents_including_orchestrator():
    assert DEFAULT_AGENTS is DEFAULT_AGENT_DEFINITIONS
    assert len(DEFAULT_AGENT_DEFINITIONS) == 7

    canonical_ids = {item["agent_id"] for item in DEFAULT_AGENT_DEFINITIONS}
    assert canonical_ids == {
        "security",
        "quality",
        "performance",
        "documentation",
        "test",
        "semantic",
        "orchestrator",
    }

    canonical_names = {item["name"] for item in DEFAULT_AGENT_DEFINITIONS}
    assert canonical_names == {
        "Security Agent",
        "Code Quality Agent",
        "Performance Agent",
        "Documentation Agent",
        "Test Agent",
        "Semantic & Cross-File Agent",
        "Orchestrator Agent",
    }


def test_api_registry_db_and_orchestrator_stay_synchronized():
    client = TestClient(app)
    db = next(get_db())
    try:
        ensure_default_agents_seeded(db, normalize_legacy_models=True)

        resp = client.get("/api/agents")
        assert resp.status_code == 200
        api_agents = resp.json()
        assert len(api_agents) == 7

        api_ids = {a["agent_id"] for a in api_agents}
        assert "orchestrator" in api_ids
        assert api_ids == {a["agent_id"] for a in get_registered_agents(db)}

        summary = get_agent_registry_summary(db)
        assert summary["total_registered"] == 7
        assert summary["orchestrator_registered"] is True

        orchestrator = ReviewOrchestrator()
        orch_summary = orchestrator.get_registry_summary()
        assert orch_summary["total_registered"] == 7
        assert [a["agent_id"] for a in orch_summary["agents"]] == [
            a["agent_id"] for a in api_agents
        ]
    finally:
        db.close()


def test_live_agent_toggle_propagates_to_system_prompt_and_stream():
    client = TestClient(app)
    db = next(get_db())
    original_states: dict[str, bool] = {}

    try:
        ensure_default_agents_seeded(db, normalize_legacy_models=True)
        for rec in db.query(AgentConfigRecord).all():
            original_states[rec.agent_id] = bool(rec.is_enabled)
            rec.is_enabled = True
        db.commit()

        # Disable Performance and Test agents via API
        r1 = client.put("/api/agents/performance", json={"is_enabled": False})
        r2 = client.put("/api/agents/test", json={"is_enabled": False})
        assert r1.status_code == 200 and r1.json()["is_enabled"] is False
        assert r2.status_code == 200 and r2.json()["is_enabled"] is False

        prompt = _build_system_prompt(
            user_query="Which agents are currently active and which are disabled?",
            db=db,
        )
        assert "Total Registered Agents: 7" in prompt
        assert "Currently Active (Enabled) Agents: 5" in prompt
        assert "Currently Disabled Agents: 2" in prompt
        assert "Performance Agent [id: `performance` | Status: Disabled" in prompt
        assert "Test Agent [id: `test` | Status: Disabled" in prompt
        assert "Orchestrator Agent [id: `orchestrator` | Status: Active" in prompt

        # Verify live streaming chat payload inherits the exact toggled registry state
        conv = client.post("/api/conversations", json={"title": "Registry Sync Check"})
        assert conv.status_code == 201
        conv_id = conv.json()["id"]

        captured = []
        mock_llm = MagicMock()
        mock_llm.model = "nvidia/nemotron-3-ultra-550b-a55b"
        mock_llm.is_available.return_value = True

        def mock_stream(payload):
            captured.append(payload)
            yield "Nexarion has 7 registered agents, with 5 currently active."

        mock_llm.stream_chat.side_effect = mock_stream

        with patch(
            "code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm
        ):
            stream_resp = client.post(
                f"/api/conversations/{conv_id}/messages/stream",
                json={"content": "How many agents does Nexarion have right now?"},
            )
            assert stream_resp.status_code == 200

        assert len(captured) == 1
        sys_msg = captured[0][0]["content"]
        assert "Total Registered Agents: 7" in sys_msg
        assert "Currently Active (Enabled) Agents: 5" in sys_msg
        assert "Currently Disabled Agents: 2" in sys_msg
        assert "nemotron" not in sys_msg.lower()
        assert "qwen" not in sys_msg.lower()
    finally:
        for agent_id, enabled in original_states.items():
            client.put(f"/api/agents/{agent_id}", json={"is_enabled": enabled})
        db.close()


def test_explicit_model_query_detection_and_privacy_isolation():
    ordinary_queries = [
        "Who are you?",
        "What can you do?",
        "Who developed Nexarion?",
        "How many agents does Nexarion have?",
        "List all your agents and describe what each one does.",
        "Which agents are currently active and which are disabled?",
        "What is the role of the Orchestrator agent?",
        "Is Orchestrator considered an agent?",
        "Hi, how are you?",
        "Why should I use Nexarion instead of ChatGPT?",
        "Review this Python code for SQL injection and hardcoded secrets.",
    ]
    for query in ordinary_queries:
        assert _is_explicit_model_query(query) is False, f"Unexpected model match for: {query}"
        prompt = _build_system_prompt(
            provider="nvidia",
            model="nvidia/nemotron-3-ultra-550b-a55b",
            user_query=query,
        )
        lowered = prompt.lower()
        for hidden_token in ("nemotron", "qwen", "nvidia", "gemini", "claude", "ollama"):
            assert hidden_token not in lowered, f"Leaked '{hidden_token}' on query '{query}'"

        assert "Total Registered Agents: 7" in prompt
        assert "Orchestrator Agent" in prompt
        assert "Emoji & Tone Guidance:" in prompt
        assert "Keep formal security audit reports" in prompt

    explicit_queries = [
        "Which LLM are you using?",
        "Which AI model are you using?",
        "What model are you running on?",
        "Which model powers each agent?",
        "Which provider is powering Nexarion?",
        "Are you using Gemini or Nemotron?",
        "Are you using ChatGPT, Claude, Gemini, or Nemotron?",
    ]
    for query in explicit_queries:
        assert _is_explicit_model_query(query) is True, f"Missed explicit model query: {query}"
        nvidia_prompt = _build_system_prompt(
            provider="nvidia",
            model="nvidia/nemotron-3-ultra-550b-a55b",
            user_query=query,
        )
        assert "NVIDIA Nemotron Ultra" in nvidia_prompt
        assert "nvidia/nemotron-3-ultra-550b-a55b" in nvidia_prompt
        assert "Documentation Agent, Test Agent" in nvidia_prompt
        assert "Security Agent (Bandit + SAST)" in nvidia_prompt
        assert "Orchestrator Agent (ReviewOrchestrator)" in nvidia_prompt

        ollama_prompt = _build_system_prompt(
            provider="ollama",
            model="qwen2.5-coder:7b",
            user_query=query,
        )
        assert "local qwen2.5-coder:7b via Ollama" in ollama_prompt
