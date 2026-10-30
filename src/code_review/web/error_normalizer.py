from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

RE_API_KEY = re.compile(r"nvapi-[A-Za-z0-9_\-]+", re.IGNORECASE)
RE_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)
RE_SECRET = re.compile(r"(api[_-]?key|token|password|secret)=['\"][^'\"]+['\"]", re.IGNORECASE)


def sanitize_log(text: str) -> str:
    if not text:
        return ""
    text = RE_API_KEY.sub("nvapi-[REDACTED]", text)
    text = RE_BEARER.sub("Bearer [REDACTED]", text)
    text = RE_SECRET.sub(r"\1='[REDACTED]'", text)
    return text


class AIErrorResponse:
    def __init__(
        self,
        error_code: str,
        user_message: str,
        retryable: bool,
        status_code: int = 500,
    ) -> None:
        self.error_code = error_code
        self.user_message = user_message
        self.retryable = retryable
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "user_message": self.user_message,
            "retryable": self.retryable,
        }


def normalize_ai_error(exc: Exception, provider_name: str | None = None) -> AIErrorResponse:
    raw_msg = str(exc)
    msg = raw_msg.lower()
    exc_type = type(exc).__name__.lower()

    sanitized_trace = sanitize_log(f"AI generation exception ({exc_type}): {raw_msg}")
    logger.error("[AI ERROR] provider=%s details=%s", provider_name or "unknown", sanitized_trace)

    if (
        "timeout" in msg
        or "timed out" in msg
        or "timeout" in exc_type
        or "timeoutexception" in exc_type
    ):
        return AIErrorResponse(
            error_code="TIMEOUT",
            user_message="NEXARION couldn't get a response in time. Please try again.",
            retryable=True,
            status_code=504,
        )

    if "rate limit" in msg or "429" in msg or "too many requests" in msg:
        return AIErrorResponse(
            error_code="RATE_LIMITED",
            user_message="Too many requests right now. Please wait a moment and try again.",
            retryable=True,
            status_code=429,
        )

    if (
        "context length" in msg
        or "too large" in msg
        or "maximum context" in msg
        or "tokens exceeded" in msg
        or "413" in msg
    ):
        return AIErrorResponse(
            error_code="REQUEST_TOO_LARGE",
            user_message=(
                "This request is too large to process. Try shortening it or splitting it "
                "into smaller parts."
            ),
            retryable=False,
            status_code=400,
        )

    if (
        "unauthorized" in msg
        or "401" in msg
        or "403" in msg
        or "forbidden" in msg
        or "api_key" in msg
        or "invalid api key" in msg
        or "authentication" in msg
        or "not configured or empty" in msg
    ):
        return AIErrorResponse(
            error_code="AUTH_OR_ACCESS_ISSUE",
            user_message="The selected model couldn't be accessed. Check your AI configuration.",
            retryable=False,
            status_code=401,
        )

    if (
        (
            "model" in msg
            and (
                "not found" in msg
                or "does not exist" in msg
                or "unknown" in msg
                or "not configured" in msg
                or "isn't configured" in msg
                or "invalid" in msg
            )
        )
        or "unknown model" in msg
        or "unsupported ai model" in msg
        or "model not found" in msg
        or "model isn't configured" in msg
        or "model is not configured" in msg
    ):
        return AIErrorResponse(
            error_code="INVALID_MODEL_CONFIG",
            user_message="This model isn't configured correctly. Please check AI Settings.",
            retryable=False,
            status_code=400,
        )

    if ("attachment" in msg or "attachments" in msg) and (
        "not found" in msg or "access is denied" in msg or "unauthorized" in msg
    ):
        return AIErrorResponse(
            error_code="ATTACHMENT_NOT_FOUND",
            user_message=(
                "The attached file could not be found or accessed. "
                "Please re-attach the file and try again."
            ),
            retryable=False,
            status_code=404,
        )

    if (
        "unsupported file" in msg
        or "unsupported attachment" in msg
        or "supported formats include" in msg
    ):
        return AIErrorResponse(
            error_code="UNSUPPORTED_ATTACHMENT_TYPE",
            user_message=(
                "The attached file type is not supported. "
                "Please upload a .pdf, .txt, .diff, .patch, or code file."
            ),
            retryable=False,
            status_code=400,
        )

    if (
        "could not decode" in msg
        or "binary data detected" in msg
        or "contains no readable text" in msg
        or "extraction" in msg
        or "corrupted or malformed" in msg
    ):
        return AIErrorResponse(
            error_code="FILE_DECODING_ERROR",
            user_message=(
                "Could not read the attached file. Ensure it is a valid text "
                "or diff file with supported encoding."
            ),
            retryable=False,
            status_code=422,
        )

    if "stream interrupted" in msg or "connection reset" in msg or "broken pipe" in msg:
        return AIErrorResponse(
            error_code="STREAM_INTERRUPTED",
            user_message="The response stream was interrupted. Please retry your request.",
            retryable=True,
            status_code=500,
        )

    if (
        "connection refused" in msg
        or "cannot connect" in msg
        or "failed to connect" in msg
        or "connection error" in msg
        or "connectionerror" in exc_type
        or "urlerror" in exc_type
        or "connecterror" in exc_type
        or "getaddrinfo" in msg
        or "name resolution" in msg
    ):
        return AIErrorResponse(
            error_code="NETWORK_FAILURE",
            user_message="Couldn't connect to the AI service. Check your connection and retry.",
            retryable=True,
            status_code=503,
        )

    if (
        "503" in msg
        or "502" in msg
        or "unavailable" in msg
        or "service unavailable" in msg
        or "overloaded" in msg
        or "bad gateway" in msg
    ):
        return AIErrorResponse(
            error_code="SERVICE_UNAVAILABLE",
            user_message="The AI service is temporarily unavailable. Please try again shortly.",
            retryable=True,
            status_code=503,
        )

    return AIErrorResponse(
        error_code="GENERATION_FAILED",
        user_message="Something went wrong while generating your response. Please try again.",
        retryable=True,
        status_code=500,
    )
