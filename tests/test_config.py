import pytest
from pydantic import ValidationError

from code_review.config import Settings, get_settings


class TestSettingsDefaults:
    def test_default_log_level(self) -> None:
        settings = Settings(log_level="INFO")
        assert settings.log_level == "INFO"

    def test_default_app_name(self) -> None:
        settings = Settings()
        assert settings.app_name == "multi-agent-code-review"

    def test_default_debug_is_false(self) -> None:
        settings = Settings()
        assert settings.debug is False

    def test_default_llm_settings(self) -> None:
        settings = Settings()
        assert settings.llm_provider == "ollama"
        assert settings.llm_model == "qwen2.5-coder:7b"
        assert settings.llm_base_url == "http://localhost:11434"
        assert settings.llm_timeout_seconds == 60.0
        assert settings.llm_temperature == 0.1


class TestSettingsFromEnvironment:
    def test_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = Settings()

        assert settings.log_level == "DEBUG"

    def test_debug_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG", "true")
        settings = Settings()
        assert settings.debug is True

    def test_llm_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MODEL", "qwen2.5-coder:1.5b")
        monkeypatch.setenv("LLM_BASE_URL", "http://remote-server:11434")
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30.0")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.2")

        settings = Settings()
        assert settings.llm_model == "qwen2.5-coder:1.5b"
        assert settings.llm_base_url == "http://remote-server:11434"
        assert settings.llm_timeout_seconds == 30.0
        assert settings.llm_temperature == 0.2


class TestSettingsValidation:
    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(log_level="VERBOSE")  # type: ignore[arg-type]

    def test_invalid_debug_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(debug="banana")  # type: ignore[arg-type]


class TestGetSettings:
    def test_returns_settings_instance(self) -> None:
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        get_settings.cache_clear()
        first = get_settings()
        second = get_settings()
        assert first is second
