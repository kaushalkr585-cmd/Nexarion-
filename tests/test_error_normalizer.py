from code_review.llm.client import OllamaConnectionError, OllamaResponseError, OllamaTimeoutError
from code_review.llm.nemotron_client import NemotronConnectionError, NemotronTimeoutError
from code_review.web.error_normalizer import normalize_ai_error, sanitize_log


def test_timeout_error_normalization():
    err1 = OllamaTimeoutError("Request to Ollama timed out after 60s")
    norm1 = normalize_ai_error(err1, "ollama")
    assert norm1.error_code == "TIMEOUT"
    assert norm1.user_message == "NEXARION couldn't get a response in time. Please try again."
    assert norm1.retryable is True
    assert norm1.status_code == 504
    assert "ollama" not in norm1.user_message.lower()

    err2 = NemotronTimeoutError("Request to NVIDIA NIM timed out after 40.0s")
    norm2 = normalize_ai_error(err2, "nvidia")
    assert norm2.error_code == "TIMEOUT"
    assert norm2.user_message == "NEXARION couldn't get a response in time. Please try again."
    assert "nvidia" not in norm2.user_message.lower()
    assert "nim" not in norm2.user_message.lower()


def test_connection_and_network_error_normalization():
    err = OllamaConnectionError(
        "Cannot connect to Ollama at http://localhost:11434: Connection refused"
    )
    norm = normalize_ai_error(err, "ollama")
    assert norm.error_code == "NETWORK_FAILURE"
    assert (
        norm.user_message == "Couldn't connect to the AI service. Check your connection and retry."
    )
    assert norm.retryable is True
    assert "localhost" not in norm.user_message
    assert "ollama" not in norm.user_message.lower()


def test_auth_error_normalization():
    err = NemotronConnectionError("NVIDIA_API_KEY is not configured or empty.")
    norm = normalize_ai_error(err, "nvidia")
    assert norm.error_code == "AUTH_OR_ACCESS_ISSUE"
    assert (
        norm.user_message
        == "The selected model couldn't be accessed. Check your AI configuration."
    )
    assert norm.retryable is False
    assert "nvidia_api_key" not in norm.user_message.lower()


def test_rate_limit_normalization():
    err = OllamaResponseError("HTTP 429: Too Many Requests - rate limit exceeded")
    norm = normalize_ai_error(err, "ollama")
    assert norm.error_code == "RATE_LIMITED"
    assert norm.user_message == "Too many requests right now. Please wait a moment and try again."
    assert norm.retryable is True


def test_context_length_normalization():
    err = Exception("maximum context length is 8192 tokens, but request was 12000 tokens")
    norm = normalize_ai_error(err, "nvidia")
    assert norm.error_code == "REQUEST_TOO_LARGE"
    assert norm.user_message == (
        "This request is too large to process. Try shortening it or splitting it "
        "into smaller parts."
    )
    assert norm.retryable is False


def test_service_unavailable_normalization():
    err = Exception("503 Service Unavailable: server overloaded")
    norm = normalize_ai_error(err, "nvidia")
    assert norm.error_code == "SERVICE_UNAVAILABLE"
    assert (
        norm.user_message == "The AI service is temporarily unavailable. Please try again shortly."
    )
    assert norm.retryable is True


def test_sanitize_log_masks_secrets():
    raw = (
        "Request failed with key "
        "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 "
        "and Bearer secret_token_abc"
    )
    clean = sanitize_log(raw)
    assert "nvapi-Hge6OY" not in clean
    assert "nvapi-[REDACTED]" in clean
    assert "secret_token_abc" not in clean
    assert "Bearer [REDACTED]" in clean
