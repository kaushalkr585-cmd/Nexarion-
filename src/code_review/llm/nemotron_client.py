from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from code_review.llm.client import (
    OllamaClientError,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)

logger = logging.getLogger(__name__)


class NemotronClientError(OllamaClientError):
        pass


class NemotronConnectionError(OllamaConnectionError, NemotronClientError):
        pass


class NemotronTimeoutError(OllamaTimeoutError, NemotronClientError):
        pass


class NemotronResponseError(OllamaResponseError, NemotronClientError):
        pass


class NemotronClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/nemotron-3-ultra-550b-a55b",
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        clean_model = model.strip() if isinstance(model, str) else ""
        if not clean_model or clean_model.lower() in ("llm", "nvidia", "default", "none"):
            clean_model = "nvidia/nemotron-3-ultra-550b-a55b"
        self.model = clean_model
        self.timeout = timeout
        self.temperature = temperature

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        models_url = f"{self.base_url}/models"
        try:
            req = urllib.request.Request(
                models_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=min(5.0, self.timeout)) as resp:  # nosec B310
                return resp.status == 200
        except Exception as exc:
            logger.debug("Nemotron availability check failed: %s", exc)
            return False

    def list_models(self) -> list[str]:
        if not self.api_key:
            return []
        models_url = f"{self.base_url}/models"
        try:
            req = urllib.request.Request(
                models_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=min(6.0, self.timeout)) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("data", [])
                return [m.get("id", "") for m in models if "nemotron" in m.get("id", "").lower()]
        except Exception as exc:
            logger.warning("Could not list Nemotron models: %s", exc)
            return [self.model]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_format: bool = True,
        temperature: float | None = None,
    ) -> str:
        if not self.api_key:
            raise NemotronConnectionError("NVIDIA_API_KEY is not configured or empty.")

        chat_url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": 4096,
        }
        if json_format:
            payload["response_format"] = {"type": "json_object"}

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            chat_url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    return ""
                content = choices[0].get("message", {}).get("content", "")
                return content
        except TimeoutError as exc:
            logger.error("Nemotron request timed out after %.1fs", self.timeout)
            raise NemotronTimeoutError(
                f"Request to NVIDIA NIM timed out after {self.timeout}s"
            ) from exc
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error("Nemotron HTTP error %d: %s (%s)", exc.code, exc.reason, err_body)
            raise NemotronResponseError(
                f"NVIDIA HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("Failed to connect to NVIDIA NIM: %s", exc.reason)
            raise NemotronConnectionError(
                f"Cannot connect to NVIDIA NIM at {chat_url}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from NVIDIA NIM: %s", exc)
            raise NemotronResponseError(f"Invalid JSON returned from NVIDIA NIM: {exc}") from exc

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        if not self.api_key:
            raise NemotronConnectionError("NVIDIA_API_KEY is not configured or empty.")

        chat_url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            chat_url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or line_str.startswith(":"):
                        continue
                    if line_str == "data: [DONE]":
                        break
                    if line_str.startswith("data: "):
                        json_str = line_str[6:].strip()
                        if json_str:
                            try:
                                data = json.loads(json_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except TimeoutError as exc:
            logger.error("Nemotron streaming timed out after %.1fs", self.timeout)
            raise NemotronTimeoutError(
                f"Request to NVIDIA NIM timed out after {self.timeout}s"
            ) from exc
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "Nemotron streaming HTTP error %d: %s (%s)", exc.code, exc.reason, err_body
            )
            raise NemotronResponseError(
                f"NVIDIA HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("Failed to connect to NVIDIA NIM: %s", exc.reason)
            raise NemotronConnectionError(
                f"Cannot connect to NVIDIA NIM at {chat_url}: {exc.reason}"
            ) from exc
