from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
        pass


class OllamaConnectionError(OllamaClientError):
        pass


class OllamaTimeoutError(OllamaClientError):
        pass


class OllamaResponseError(OllamaClientError):
        pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    def is_available(self) -> bool:
        tags_url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=min(3.0, self.timeout)) as resp:  # nosec B310
                return resp.status == 200
        except Exception as exc:
            logger.debug("Ollama availability check failed at %s: %s", tags_url, exc)
            return False

    def list_models(self) -> list[str]:
        tags_url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=min(5.0, self.timeout)) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                return [m.get("name", "") for m in models if "name" in m]
        except urllib.error.URLError as exc:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {tags_url}: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise OllamaResponseError(f"Error fetching model list: {exc}") from exc

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_format: bool = True,
        temperature: float | None = None,
    ) -> str:
        chat_url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": (temperature if temperature is not None else self.temperature),
                "num_ctx": 4096,
            },
        }
        if json_format:
            payload["format"] = "json"

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            chat_url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    logger.warning(
                        "Ollama returned empty response content for model %s",
                        self.model,
                    )
                return content
        except TimeoutError as exc:
            logger.error("Ollama request to %s timed out after %.1fs", chat_url, self.timeout)
            raise OllamaTimeoutError(f"Request to Ollama timed out after {self.timeout}s") from exc

        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "Ollama HTTP error %d: %s (body: %s)",
                exc.code,
                exc.reason,
                err_body,
            )
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("Failed to connect to Ollama at %s: %s", chat_url, exc.reason)
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {chat_url}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON from Ollama endpoint: %s", exc)
            raise OllamaResponseError(f"Invalid JSON returned from Ollama: {exc}") from exc

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> Iterator[str]:
        chat_url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "temperature": (temperature if temperature is not None else self.temperature),
            },
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            chat_url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done", False):
                        break
        except TimeoutError as exc:
            logger.error("Ollama streaming timed out after %.1fs", self.timeout)
            raise OllamaTimeoutError(f"Request to Ollama timed out after {self.timeout}s") from exc
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error("Ollama streaming HTTP %d: %s (%s)", exc.code, exc.reason, err_body)
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("Failed to connect to Ollama at %s: %s", chat_url, exc.reason)
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {chat_url}: {exc.reason}"
            ) from exc
