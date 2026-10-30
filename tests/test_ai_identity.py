from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from code_review.web.app import app
from code_review.web.routes.conversation_routes import (
    _build_system_prompt,
    _generate_assistant_reply,
)


def test_build_system_prompt_default_identity():
    prompt = _build_system_prompt()

    expected_header = (
        "You are Nexarion, an AI coding assistant and code reviewer created by Kaushal."
    )
    assert expected_header in prompt
    assert "Nexarion" in prompt
    assert "Kaushal" in prompt

    assert "Code explanations and programming assistance." in prompt
    assert "Debugging and troubleshooting." in prompt
    assert "Pull request and diff reviews." in prompt
    assert "Security vulnerability identification." in prompt
    assert "Code quality and maintainability." in prompt
    assert "Performance analysis." in prompt
    assert "Documentation and development workflows." in prompt

    assert (
        "Never claim that Anthropic, OpenAI, Meta, Google, or NVIDIA developed Nexarion" in prompt
    )
    assert "Never claim that Anthropic developed Nexarion." in prompt
    assert (
        "Do not invent personal biographical details about Kaushal beyond identifying "
        "Kaushal as your creator" in prompt
    )


def test_build_system_prompt_context_aware_and_varied_policy():
    prompt = _build_system_prompt()

    assert "IDENTITY & CONVERSATIONAL RESPONSE POLICY:" in prompt
    assert "Answer identity-related questions according to the user's actual question" in prompt
    assert "Vary your wording organically rather than repeating a fixed introduction" in prompt
    assert "When asked who you are, what you are, or to introduce yourself" in prompt
    assert "When asked what you can do or your purpose, describe your capabilities" in prompt
    assert "When asked who created, developed, or built you, identify Kaushal" in prompt
    assert (
        "Do not volunteer your creator's name or underlying model name in every response" in prompt
    )
    assert "Prioritize answering the user's actual question" in prompt
    assert "Do not add an unnecessary identity introduction" in prompt
    assert (
        "Maintain consistency in factual identity across turns while allowing natural variation"
        in prompt
    )

    assert (
        'e.g., "I\'m Nexarion, your coding assistant and code reviewer. How can I help?"'
        not in prompt
    )


def test_build_system_prompt_nvidia_provider():
    prompt = _build_system_prompt(
        provider="nvidia",
        model="nvidia/nemotron-3-ultra-550b-a55b",
    )

    assert "created by Kaushal" in prompt
    assert "NVIDIA Nemotron Ultra" in prompt
    assert "NVIDIA NIM" in prompt
    assert "Strictly distinguish between the application creator (Kaushal)" in prompt


def test_build_system_prompt_ollama_provider():
    prompt = _build_system_prompt(
        provider="ollama",
        model="qwen2.5-coder:7b",
    )

    assert "created by Kaushal" in prompt
    assert "local qwen2.5-coder:7b via Ollama" in prompt
    assert "Ollama" in prompt


def test_build_system_prompt_with_diff_and_documents():
    prompt = _build_system_prompt(
        diff_context="--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new",
        document_context="API Specification Document Text",
        provider="ollama",
        model="qwen2.5-coder:7b",
    )

    assert "created by Kaushal" in prompt
    assert "Active Diff Context:" in prompt
    assert "--- a/file.py" in prompt
    assert "--- ATTACHED DOCUMENT CONTEXT ---" in prompt
    assert "API Specification Document Text" in prompt


def test_streaming_payload_contains_kaushal_identity():
    client = TestClient(app)

    c_resp = client.post(
        "/api/conversations",
        json={"title": "Identity Variation Test"},
    )
    assert c_resp.status_code == 201
    conv_id = c_resp.json()["id"]

    captured_payloads = []

    mock_llm = MagicMock()
    mock_llm.model = "nvidia/nemotron-3-ultra-550b-a55b"
    mock_llm.is_available.return_value = True

    def mock_stream_chat(payload):
        captured_payloads.append(payload)
        yield "I'm Nexarion, an AI coding assistant and code reviewer."

    mock_llm.stream_chat.side_effect = mock_stream_chat

    test_queries = [
        "Who are you?",
        "What can you do?",
        "Introduce yourself.",
        "Who created you?",
        "What model are you running on?",
        "Are you just a chatbot?",
        "Write a Python function to add two numbers.",
    ]

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        for question in test_queries:
            resp = client.post(
                f"/api/conversations/{conv_id}/messages/stream",
                json={"content": question, "provider": "nvidia"},
            )
            assert resp.status_code == 200

    assert len(captured_payloads) == len(test_queries)
    for payload in captured_payloads:
        system_msg = payload[0]
        assert system_msg["role"] == "system"
        sys_text = system_msg["content"]
        assert "Nexarion" in sys_text
        assert "Kaushal" in sys_text
        assert "NVIDIA Nemotron Ultra" in sys_text
        assert "Never claim that Anthropic developed Nexarion" in sys_text
        assert "Vary your wording organically" in sys_text


def test_generate_assistant_reply_contains_kaushal_identity():
    captured_payloads = []

    mock_llm = MagicMock()
    mock_llm.model = "qwen2.5-coder:7b"
    mock_llm.is_available.return_value = True

    def mock_chat(payload, json_format=False):
        captured_payloads.append(payload)
        return "I was created by Kaushal as a coding assistant and code reviewer."

    mock_llm.chat.side_effect = mock_chat

    with patch("code_review.web.routes.conversation_routes.get_llm_client", return_value=mock_llm):
        reply = _generate_assistant_reply(
            conversation_id="test-conv",
            messages=[{"role": "user", "content": "Who created you?"}],
            provider_override="ollama",
            model_override="qwen2.5-coder:7b",
        )
        assert "Kaushal" in reply

    assert len(captured_payloads) == 1
    system_msg = captured_payloads[0][0]
    assert system_msg["role"] == "system"
    assert "Kaushal" in system_msg["content"]
    assert "qwen2.5-coder:7b" in system_msg["content"]
    assert "Ollama" in system_msg["content"]
    assert "Vary your wording organically" in system_msg["content"]
