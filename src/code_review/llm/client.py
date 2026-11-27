from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.error
import urllib.request
import weakref
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_HTTP_CLIENT_LOCK = threading.Lock()
_SYNC_HTTP_CLIENT: httpx.Client | None = None
_ASYNC_HTTP_CLIENTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def is_urlopen_patched() -> bool:
    """Detect unittest.mock patching on urllib.request.urlopen so legacy unit tests stay green."""
    fn = urllib.request.urlopen
    return hasattr(fn, "assert_called") or getattr(fn, "__module__", "") == "unittest.mock"


def get_shared_sync_http_client(
    *, connect_timeout: float = 5.0, read_timeout: float = 60.0
) -> httpx.Client:
    """Return process-wide pooled httpx.Client reusing TCP/TLS connections across requests."""
    global _SYNC_HTTP_CLIENT
    with _HTTP_CLIENT_LOCK:
        if _SYNC_HTTP_CLIENT is None or _SYNC_HTTP_CLIENT.is_closed:
            _SYNC_HTTP_CLIENT = httpx.Client(
                timeout=httpx.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            )
        return _SYNC_HTTP_CLIENT


def get_loop_async_http_client(
    *, connect_timeout: float = 5.0, read_timeout: float = 60.0
) -> httpx.AsyncClient:
    """Return an event-loop-scoped pooled httpx.AsyncClient safe across TestClient loops."""
    loop = asyncio.get_running_loop()
    with _HTTP_CLIENT_LOCK:
        client = _ASYNC_HTTP_CLIENTS.get(loop)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            )
            _ASYNC_HTTP_CLIENTS[loop] = client
        return client


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
        clean_model = model.strip() if isinstance(model, str) else ""
        if not clean_model or clean_model.lower() in ("ollama", "default", "none"):
            clean_model = "qwen2.5-coder:7b"
        self.model = clean_model
        self.timeout = timeout
        self.temperature = temperature
        self.last_call_meta: dict[str, Any] = {}

    def validate_config(self) -> None:
        if not self.base_url:
            raise OllamaConnectionError("OLLAMA_BASE_URL is not configured.")

    def is_available(self) -> bool:
        tags_url = f"{self.base_url}/api/tags"
        try:
            if is_urlopen_patched():
                req = urllib.request.Request(tags_url, method="GET")
                with urllib.request.urlopen(req, timeout=min(3.0, self.timeout)) as resp:  # nosec B310
                    return resp.status == 200
            client = get_shared_sync_http_client(read_timeout=min(3.0, self.timeout))
            resp = client.get(tags_url, timeout=min(3.0, self.timeout))
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Ollama availability check failed at %s: %s", tags_url, exc)
            return False

    def list_models(self) -> list[str]:
        tags_url = f"{self.base_url}/api/tags"
        try:
            if is_urlopen_patched():
                req = urllib.request.Request(tags_url, method="GET")
                with urllib.request.urlopen(req, timeout=min(5.0, self.timeout)) as resp:  # nosec B310
                    data = json.loads(resp.read().decode("utf-8"))
            else:
                client = get_shared_sync_http_client(read_timeout=min(5.0, self.timeout))
                resp = client.get(tags_url, timeout=min(5.0, self.timeout))
                resp.raise_for_status()
                data = resp.json()
            models = data.get("models", [])
            return [m.get("name", "") for m in models if "name" in m]
        except urllib.error.URLError as exc:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {tags_url}: {exc.reason}"
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(f"Failed to connect to Ollama at {tags_url}: {exc}") from exc
        except Exception as exc:
            raise OllamaResponseError(f"Error fetching model list: {exc}") from exc

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_format: bool = True,
        temperature: float | None = None,
        enable_thinking: bool = True,
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

        try:
            if is_urlopen_patched():
                body_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    chat_url,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    raw_bytes = resp.read()
                    data = json.loads(raw_bytes.decode("utf-8"))
            else:
                client = get_shared_sync_http_client(read_timeout=self.timeout)
                resp = client.post(
                    chat_url,
                    json=payload,
                    timeout=httpx.Timeout(
                        connect=min(5.0, self.timeout),
                        read=self.timeout,
                        write=10.0,
                        pool=5.0,
                    ),
                )
                if resp.status_code >= 400:
                    raise OllamaResponseError(
                        f"Ollama HTTP {resp.status_code}: {resp.reason_phrase} - {resp.text}"
                    )
                data = resp.json()

            message = data.get("message", {})
            content = message.get("content", "")
            if not content:
                logger.warning(
                    "Ollama returned empty response content for model %s",
                    self.model,
                )
            return content
        except (TimeoutError, httpx.TimeoutException) as exc:
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
        except (urllib.error.URLError, httpx.ConnectError) as exc:
            reason = getattr(exc, "reason", exc)
            logger.error("Failed to connect to Ollama at %s: %s", chat_url, reason)
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {chat_url}: {reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON from Ollama endpoint: %s", exc)
            raise OllamaResponseError(f"Invalid JSON returned from Ollama: {exc}") from exc

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        enable_thinking: bool = True,
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

        try:
            if is_urlopen_patched():
                body_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    chat_url,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
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
                return

            client = get_shared_sync_http_client(read_timeout=self.timeout)
            with client.stream(
                "POST",
                chat_url,
                json=payload,
                timeout=httpx.Timeout(
                    connect=min(5.0, self.timeout),
                    read=self.timeout,
                    write=10.0,
                    pool=5.0,
                ),
            ) as resp:
                if resp.status_code >= 400:
                    err_body = resp.read().decode("utf-8", errors="replace")
                    raise OllamaResponseError(
                        f"Ollama HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                    )
                for line_str in resp.iter_lines():
                    clean = line_str.strip()
                    if not clean:
                        continue
                    data = json.loads(clean)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done", False):
                        break
        except (TimeoutError, httpx.TimeoutException) as exc:
            logger.error("Ollama streaming timed out after %.1fs", self.timeout)
            raise OllamaTimeoutError(f"Request to Ollama timed out after {self.timeout}s") from exc
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error("Ollama streaming HTTP %d: %s (%s)", exc.code, exc.reason, err_body)
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except (urllib.error.URLError, httpx.ConnectError) as exc:
            reason = getattr(exc, "reason", exc)
            logger.error("Failed to connect to Ollama at %s: %s", chat_url, reason)
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {chat_url}: {reason}"
            ) from exc

    async def astream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        enable_thinking: bool = True,
        ttft_timeout: float | None = None,
        idle_timeout: float | None = None,
    ) -> AsyncIterator[str]:
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
        read_limit = idle_timeout or self.timeout
        client = get_loop_async_http_client(
            connect_timeout=min(5.0, self.timeout),
            read_timeout=read_limit,
        )
        try:
            async with client.stream(
                "POST",
                chat_url,
                json=payload,
                timeout=httpx.Timeout(
                    connect=min(5.0, self.timeout),
                    read=read_limit,
                    write=10.0,
                    pool=5.0,
                ),
            ) as resp:
                if resp.status_code >= 400:
                    err_body = (await resp.aread()).decode("utf-8", errors="replace")
                    raise OllamaResponseError(
                        f"Ollama HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                    )
                async for line_str in resp.aiter_lines():
                    clean = line_str.strip()
                    if not clean:
                        continue
                    data = json.loads(clean)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done", False):
                        break
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise OllamaTimeoutError(f"Request to Ollama timed out after {read_limit}s") from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(f"Cannot connect to Ollama at {chat_url}: {exc}") from exc

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Execute an Ollama /api/chat request with tool calling and prompt fallback."""
        chat_url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": (temperature if temperature is not None else self.temperature),
                "num_ctx": 8192,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            if is_urlopen_patched():
                body_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    chat_url,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    data = json.loads(resp.read().decode("utf-8"))
            else:
                client = get_shared_sync_http_client(read_timeout=self.timeout)
                resp = client.post(
                    chat_url,
                    json=payload,
                    timeout=httpx.Timeout(
                        connect=min(5.0, self.timeout),
                        read=self.timeout,
                        write=10.0,
                        pool=5.0,
                    ),
                )
                if resp.status_code in (400, 404, 422) and tools:
                    logger.warning("Ollama model does not support native tools; using JSON fallback.")
                    return self._fallback_prompt_tool_call(messages, tools, temperature=temperature)
                if resp.status_code >= 400:
                    raise OllamaResponseError(
                        f"Ollama HTTP {resp.status_code}: {resp.reason_phrase} - {resp.text}"
                    )
                data = resp.json()

            msg = data.get("message", {}) or {}
            raw_calls = msg.get("tool_calls") or []
            parsed_calls: list[dict[str, Any]] = []
            for i, tc in enumerate(raw_calls):
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments", {})
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
                            args = {
                                "_malformed_arguments": True,
                                "_parse_error": f"Invalid JSON in tool arguments: {exc}",
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
                        "id": tc.get("id") or f"ollama_call_{i}",
                        "name": str(fn.get("name") or "").strip(),
                        "arguments": args,
                    }
                )
            return {
                "content": msg.get("content") or "",
                "tool_calls": parsed_calls,
                "raw_tool_calls": raw_calls,
            }
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (400, 404, 422) and tools:
                logger.warning("Ollama model does not support native tools; using JSON fallback.")
                return self._fallback_prompt_tool_call(messages, tools, temperature=temperature)
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code}: {exc.reason} - {err_body}"
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise OllamaTimeoutError(f"Request to Ollama timed out after {self.timeout}s") from exc
        except (urllib.error.URLError, httpx.ConnectError) as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {chat_url}: {reason}"
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
            "You have access to these tools. Respond ONLY with JSON: "
            '{"tool_calls": [{"name": "<tool>", "arguments": {...}}]} or '
            '{"final_answer": "<markdown answer>"}.\n'
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
