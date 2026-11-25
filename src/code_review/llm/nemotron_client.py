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

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Execute a chat completion with OpenAI-style tool definitions and parse tool calls."""
        if not self.api_key:
            raise NemotronConnectionError("NVIDIA_API_KEY is not configured or empty.")

        chat_url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

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
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    return {"content": "", "tool_calls": []}
                msg = choices[0].get("message", {}) or {}
                raw_calls = msg.get("tool_calls") or []
                parsed_calls: list[dict[str, Any]] = []
                for tc in raw_calls:
                    fn = tc.get("function") or {}
                    raw_args = fn.get("arguments", "{}")
                    parse_error: str | None = None
                    if isinstance(raw_args, str):
                        stripped = raw_args.strip()
                        if not stripped:
                            args = {}
                        else:
                            try:
                                loaded = json.loads(stripped)
                                if isinstance(loaded, dict):
                                    args = loaded
                                else:
                                    args = {
                                        "_malformed_arguments": True,
                                        "_parse_error": "Tool arguments JSON must decode to an object.",
                                        "_raw_arguments": raw_args[:500],
                                    }
                            except json.JSONDecodeError as exc:
                                parse_error = str(exc)
                                args = {
                                    "_malformed_arguments": True,
                                    "_parse_error": f"Invalid JSON in tool arguments: {parse_error}",
                                    "_raw_arguments": raw_args[:500],
                                }
                    elif isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        args = {
                            "_malformed_arguments": True,
                            "_parse_error": f"Unsupported tool arguments type: {type(raw_args).__name__}",
                        }
                    parsed_calls.append(
                        {
                            "id": tc.get("id") or f"call_{len(parsed_calls)}",
                            "name": str(fn.get("name") or "").strip(),
                            "arguments": args,
                        }
                    )
                return {
                    "content": msg.get("content") or "",
                    "tool_calls": parsed_calls,
                    "raw_tool_calls": raw_calls,
                    "finish_reason": choices[0].get("finish_reason"),
                }
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (400, 404, 422) and tools and "tool" in err_body.lower():
                logger.warning(
                    "Model rejected native tools (%s); falling back to prompt adapter.", exc.code
                )
                return self._fallback_prompt_tool_call(messages, tools, temperature=temperature)
            raise NemotronResponseError(
                f"NVIDIA HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except TimeoutError as exc:
            raise NemotronTimeoutError(
                f"Request to NVIDIA NIM timed out after {self.timeout}s"
            ) from exc
        except urllib.error.URLError as exc:
            raise NemotronConnectionError(
                f"Cannot connect to NVIDIA NIM at {chat_url}: {exc.reason}"
            ) from exc

    def _fallback_prompt_tool_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        tool_summaries = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "parameters": t["function"].get("parameters", {}),
            }
            for t in tools
            if "function" in t
        ]
        adapter_sys = (
            "You have access to the following tools (JSON schemas below). "
            "To call one or more tools, respond ONLY with JSON matching: "
            '{"tool_calls": [{"name": "<tool_name>", "arguments": {...}}]}. '
            "If no more tools are needed, respond ONLY with JSON: "
            '{"final_answer": "<your complete markdown response>"}.\n\n'
            f"TOOLS:\n{json.dumps(tool_summaries)}"
        )
        plain_msgs = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
            if m.get("role") in ("system", "user", "assistant")
        ]
        plain_msgs.insert(0, {"role": "system", "content": adapter_sys})
        raw = self.chat(plain_msgs, json_format=True, temperature=temperature)
        try:
            parsed = json.loads(raw)
            calls = parsed.get("tool_calls") or []
            norm_calls = [
                {
                    "id": f"fb_call_{i}",
                    "name": c.get("name", ""),
                    "arguments": c.get("arguments")
                    if isinstance(c.get("arguments"), dict)
                    else {},
                }
                for i, c in enumerate(calls)
                if isinstance(c, dict) and c.get("name")
            ]
            if norm_calls:
                return {"content": "", "tool_calls": norm_calls, "raw_tool_calls": []}
            return {
                "content": parsed.get("final_answer") or raw,
                "tool_calls": [],
                "raw_tool_calls": [],
            }
        except json.JSONDecodeError:
            return {"content": raw, "tool_calls": [], "raw_tool_calls": []}
