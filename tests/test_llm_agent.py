from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_review.agents.base import BaseAgent
from code_review.agents.llm_agent import LLMAgent
from code_review.llm.client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from code_review.llm.prompts import (
    format_diff_for_review,
    parse_llm_findings,
)
from code_review.models.enums import AgentType, Category, Severity
from code_review.models.finding import Finding
from code_review.orchestrator import ReviewOrchestrator, default_agents
from code_review.parsers.diff_parser import parse_diff

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_logic_diff_file():
    diff_path = FIXTURES_DIR / "sample_logic.diff"
    diff_text = diff_path.read_text(encoding="utf-8")
    diff_files = parse_diff(diff_text)
    assert len(diff_files) == 1
    return diff_files[0]


class TestOllamaClient:
    def test_init_defaults_and_custom(self) -> None:
        client = OllamaClient()
        assert client.base_url == "http://localhost:11434"
        assert client.model == "qwen2.5-coder:7b"
        assert client.timeout == 60.0
        assert client.temperature == 0.1

        custom = OllamaClient(
            base_url="http://192.168.1.100:11434/",
            model="qwen2.5-coder:1.5b",
            timeout=15.0,
            temperature=0.3,
        )
        assert custom.base_url == "http://192.168.1.100:11434"
        assert custom.model == "qwen2.5-coder:1.5b"
        assert custom.timeout == 15.0
        assert custom.temperature == 0.3

    @patch("urllib.request.urlopen")
    def test_is_available_true_when_200(self, mock_urlopen) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        assert client.is_available() is True

    @patch("urllib.request.urlopen")
    def test_is_available_false_on_connection_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        client = OllamaClient()
        assert client.is_available() is False

    @patch("urllib.request.urlopen")
    def test_list_models_success(self, mock_urlopen) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {"models": [{"name": "qwen2.5-coder:7b"}, {"name": "llama3:latest"}]}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        models = client.list_models()
        assert models == ["qwen2.5-coder:7b", "llama3:latest"]

    @patch("urllib.request.urlopen")
    def test_list_models_connection_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        client = OllamaClient()
        with pytest.raises(OllamaConnectionError):
            client.list_models()

    @patch("urllib.request.urlopen")
    def test_chat_success_with_json_format(self, mock_urlopen) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {"message": {"role": "assistant", "content": '{"findings": []}'}}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        reply = client.chat([{"role": "user", "content": "review this"}], json_format=True)
        assert reply == '{"findings": []}'

        args, kwargs = mock_urlopen.call_args
        req = args[0]
        assert req.get_method() == "POST"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "qwen2.5-coder:7b"
        assert payload["format"] == "json"
        assert payload["options"]["temperature"] == 0.1

    @patch("urllib.request.urlopen")
    def test_chat_timeout_raises_ollama_timeout_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        client = OllamaClient(timeout=5.0)
        with pytest.raises(OllamaTimeoutError):
            client.chat([{"role": "user", "content": "test"}])

    @patch("urllib.request.urlopen")
    def test_chat_connection_error_raises_ollama_connection_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        client = OllamaClient()
        with pytest.raises(OllamaConnectionError):
            client.chat([{"role": "user", "content": "test"}])

    @patch("urllib.request.urlopen")
    def test_chat_http_error_raises_ollama_response_error(self, mock_urlopen) -> None:
        error_file = io.BytesIO(b'{"error": "model not found"}')
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=error_file,
        )
        client = OllamaClient()
        with pytest.raises(OllamaResponseError):
            client.chat([{"role": "user", "content": "test"}])

    @patch("urllib.request.urlopen")
    def test_chat_invalid_json_body_raises_ollama_response_error(self, mock_urlopen) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"corrupted bytes"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        with pytest.raises(OllamaResponseError):
            client.chat([{"role": "user", "content": "test"}])


class TestPromptFormatting:
    def test_format_diff_shows_file_and_lines(self, sample_logic_diff_file) -> None:
        prompt = format_diff_for_review(sample_logic_diff_file)
        assert "File: src/stats.py" in prompt
        assert "calculate_average" in prompt
        assert "Added lines eligible for review" in prompt

        assert " 6" in prompt or "6" in prompt

    def test_format_diff_marks_added_lines_with_plus(self, sample_logic_diff_file) -> None:
        prompt = format_diff_for_review(sample_logic_diff_file)
        assert "+ def calculate_average" in prompt
        assert '+     f = open(filepath, "r", encoding="utf-8")' in prompt


class TestFindingParsingAndValidation:
    def test_parse_valid_findings_dict(self, sample_logic_diff_file) -> None:
        sample_json = json.dumps(
            {
                "findings": [
                    {
                        "line": 6,
                        "rule_id": "LOGIC001",
                        "message": "Potential ZeroDivisionError when values is empty.",
                        "severity": "error",
                        "category": "bug_risk",
                        "suggestion": "if not values:\n    return 0.0",
                    },
                    {
                        "line": 10,
                        "rule_id": "MUTABLE_DEFAULT",
                        "message": "Mutable default argument tags accumulates state across calls.",
                        "severity": "warning",
                        "category": "bug_risk",
                        "suggestion": "tags: list[str] | None = None",
                    },
                ]
            }
        )

        findings = parse_llm_findings(sample_json, sample_logic_diff_file)
        assert len(findings) == 2

        f0 = findings[0]
        assert f0.file == "src/stats.py"
        assert f0.line == 6
        assert f0.rule_id == "LOGIC001"
        assert f0.severity == Severity.ERROR
        assert f0.category == Category.BUG_RISK
        assert f0.agent == AgentType.LLM
        assert f0.suggestion == "if not values:\n    return 0.0"

        f1 = findings[1]
        assert f1.line == 10
        assert f1.rule_id == "MUTABLE_DEFAULT"
        assert f1.severity == Severity.WARNING
        assert f1.category == Category.BUG_RISK

    def test_parse_valid_findings_raw_list(self, sample_logic_diff_file) -> None:
        sample_json = json.dumps(
            [
                {
                    "line": 16,
                    "rule_id": "RESOURCE_LEAK",
                    "message": "File descriptor opened without context manager.",
                    "severity": "warning",
                    "category": "performance",
                    "suggestion": "with open(filepath, 'r') as f:\n    return f.read()",
                }
            ]
        )
        findings = parse_llm_findings(sample_json, sample_logic_diff_file)
        assert len(findings) == 1
        assert findings[0].line == 16
        assert findings[0].category == Category.PERFORMANCE

    def test_parse_empty_string_returns_empty(self, sample_logic_diff_file) -> None:
        assert parse_llm_findings("", sample_logic_diff_file) == []
        assert parse_llm_findings("   ", sample_logic_diff_file) == []

    def test_parse_invalid_json_returns_empty(self, sample_logic_diff_file) -> None:
        assert parse_llm_findings("Sorry, I could not review this.", sample_logic_diff_file) == []

    def test_parse_discards_hallucinated_lines_not_in_diff(self, sample_logic_diff_file) -> None:
        sample_json = json.dumps(
            {
                "findings": [
                    {
                        "line": 999,
                        "message": "Invalid line number.",
                        "severity": "error",
                        "category": "bug_risk",
                    },
                    {
                        "line": 6,
                        "message": "Valid zero division issue.",
                        "severity": "error",
                        "category": "bug_risk",
                    },
                ]
            }
        )
        findings = parse_llm_findings(sample_json, sample_logic_diff_file)
        assert len(findings) == 1
        assert findings[0].line == 6

    def test_parse_normalizes_severity_and_category(self, sample_logic_diff_file) -> None:
        sample_json = json.dumps(
            {
                "findings": [
                    {
                        "line": 6,
                        "message": "Check inputs.",
                        "severity": "HIGH",
                        "category": "QUALITY",
                    },
                    {
                        "line": 7,
                        "message": "Check docs.",
                        "severity": "informational",
                        "category": "docs",
                    },
                ]
            }
        )
        findings = parse_llm_findings(sample_json, sample_logic_diff_file)
        assert len(findings) == 2
        assert findings[0].severity == Severity.ERROR
        assert findings[0].category == Category.CODE_QUALITY
        assert findings[1].severity == Severity.INFO
        assert findings[1].category == Category.DOCUMENTATION

    def test_parse_handles_markdown_code_fences(self, sample_logic_diff_file) -> None:
        wrapped_json = (
            "```json\n"
            "{\n"
            '  "findings": [\n'
            '    {"line": 6, "message": "Wrapped in code fences.", "severity": "warning"}\n'
            "  ]\n"
            "}\n"
            "```"
        )
        findings = parse_llm_findings(wrapped_json, sample_logic_diff_file)
        assert len(findings) == 1
        assert findings[0].line == 6


class TestLLMAgent:
    def test_agent_type_is_llm(self) -> None:
        agent = LLMAgent()
        assert agent.agent_type == AgentType.LLM
        assert agent.name == "llm"
        assert isinstance(agent, BaseAgent)

    def test_review_empty_diff_returns_empty(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        agent = LLMAgent(client=mock_client)
        assert agent.review([]) == []
        mock_client.is_available.assert_not_called()

    def test_review_skips_when_ollama_unavailable(self, sample_logic_diff_file) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = False
        mock_client.base_url = "http://localhost:11434"

        agent = LLMAgent(client=mock_client)
        findings = agent.review([sample_logic_diff_file])
        assert findings == []
        mock_client.chat.assert_not_called()

    def test_review_skips_files_with_no_added_lines(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True

        diff_file = MagicMock()
        diff_file.path = "src/untouched.py"
        diff_file.added_line_numbers = frozenset()

        agent = LLMAgent(client=mock_client)
        findings = agent.review([diff_file])
        assert findings == []
        mock_client.chat.assert_not_called()

    def test_review_success_with_mocked_client(self, sample_logic_diff_file) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.model = "qwen2.5-coder:7b"
        mock_client.chat.return_value = json.dumps(
            {
                "findings": [
                    {
                        "line": 6,
                        "rule_id": "ZERO_DIV",
                        "message": "Potential division by zero when list is empty.",
                        "severity": "error",
                        "category": "bug_risk",
                        "suggestion": "if not values:\n    return 0.0",
                    }
                ]
            }
        )

        agent = LLMAgent(client=mock_client)
        findings = agent.review([sample_logic_diff_file])
        assert len(findings) == 1
        assert findings[0].line == 6
        assert findings[0].agent == AgentType.LLM
        assert findings[0].severity == Severity.ERROR
        mock_client.chat.assert_called_once()

    def test_review_timeout_handled_gracefully(self, sample_logic_diff_file) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.chat.side_effect = OllamaTimeoutError("Timed out")

        agent = LLMAgent(client=mock_client)
        findings = agent.review([sample_logic_diff_file])
        assert findings == []

    def test_review_connection_error_handled_gracefully(self, sample_logic_diff_file) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.chat.side_effect = OllamaConnectionError("Connection lost")

        agent = LLMAgent(client=mock_client)
        findings = agent.review([sample_logic_diff_file])
        assert findings == []


class TestOrchestratorWithLLMAgent:
    def test_default_agents_without_llm(self) -> None:
        agents = default_agents(include_llm=False)
        agent_types = [a.agent_type for a in agents]
        assert AgentType.AST in agent_types
        assert AgentType.RUFF in agent_types
        assert AgentType.BANDIT in agent_types
        assert AgentType.LLM not in agent_types

    def test_default_agents_with_llm(self) -> None:
        agents = default_agents(include_llm=True)
        agent_types = [a.agent_type for a in agents]
        assert AgentType.AST in agent_types
        assert AgentType.RUFF in agent_types
        assert AgentType.BANDIT in agent_types
        assert AgentType.LLM in agent_types

    def test_orchestrator_initializes_with_llm(self) -> None:
        orch = ReviewOrchestrator(include_llm=True)
        assert any(a.agent_type == AgentType.LLM for a in orch.agents)

    def test_orchestrator_runs_all_agents_including_mocked_llm(
        self, sample_logic_diff_file
    ) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.model = "qwen2.5-coder:7b"

        mock_client.chat.return_value = json.dumps(
            {
                "findings": [
                    {
                        "line": 6,
                        "rule_id": "ZERO_DIV",
                        "message": "Potential division by zero when list is empty.",
                        "severity": "error",
                        "category": "bug_risk",
                    }
                ]
            }
        )

        llm_agent = LLMAgent(client=mock_client)
        orch = ReviewOrchestrator(agents=[llm_agent])
        result = orch.review([sample_logic_diff_file])

        assert result.files_reviewed == 1
        assert result.total_findings == 1
        assert result.findings[0].agent == AgentType.LLM
        assert result.findings[0].line == 6


class TestLiveOllamaIntegration:
    @pytest.fixture
    def live_client(self):
        client = OllamaClient()
        if not client.is_available():
            pytest.skip("Local Ollama server is not online")
        models = client.list_models()

        if "qwen2.5-coder:7b" in models or any("qwen2.5-coder" in m for m in models):
            return client
        pytest.skip("No qwen2.5-coder model found in Ollama")

    def test_live_llm_review_on_sample_diff(self, live_client, sample_logic_diff_file) -> None:
        agent = LLMAgent(client=live_client)
        findings = agent.review([sample_logic_diff_file])

        assert isinstance(findings, list)
        for f in findings:
            assert isinstance(f, Finding)
            assert f.agent == AgentType.LLM
            assert f.file == "src/stats.py"
            assert f.line in sample_logic_diff_file.added_line_numbers
