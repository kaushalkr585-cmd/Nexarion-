from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx

from code_review.llm.client import (
    OllamaClientError,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
    get_loop_async_http_client,
    get_shared_sync_http_client,
    is_urlopen_patched,
)

logger = logging.getLogger(__name__)

DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
FALLBACK_NVIDIA_MODELS: tuple[str, ...] = (
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3.5-bolt-e4b",
)

_MODEL_COOLDOWN_SECONDS = 300.0
_MODEL_COOLDOWN_LOCK = threading.Lock()
_UNHEALTHY_MODELS_UNTIL: dict[str, float] = {}


def _mark_model_unhealthy(model_name: str, cooldown: float = _MODEL_COOLDOWN_SECONDS) -> None:
    if not model_name:
        return
    with _MODEL_COOLDOWN_LOCK:
        _UNHEALTHY_MODELS_UNTIL[model_name] = time.monotonic() + cooldown


def _is_model_in_cooldown(model_name: str) -> bool:
    now = time.monotonic()
    with _MODEL_COOLDOWN_LOCK:
        until = _UNHEALTHY_MODELS_UNTIL.get(model_name)
        if until is None:
            return False
        if now >= until:
            _UNHEALTHY_MODELS_UNTIL.pop(model_name, None)
            return False
        return True


def reset_model_cooldowns() -> None:
    with _MODEL_COOLDOWN_LOCK:
        _UNHEALTHY_MODELS_UNTIL.clear()

_NON_CHAT_MODEL_KEYWORDS = (
    "embed",
    "safety",
    "guard",
    "rerank",
    "parse",
    "translate",
    "nvclip",
    "cosmos",
    "video-detector",
    "gliner",
    "calibration",
)


class NemotronClientError(OllamaClientError):
    pass


class NemotronConnectionError(OllamaConnectionError, NemotronClientError):
    pass


class NemotronTimeoutError(OllamaTimeoutError, NemotronClientError):
    pass


class NemotronResponseError(OllamaResponseError, NemotronClientError):
    pass


def _is_non_retryable_status(status_code: int) -> bool:
    return status_code in (400, 401, 403, 413, 422)


def _is_model_fallback_status(status_code: int) -> bool:
    return status_code in (404, 410, 429, 502, 503, 504)


def _is_transient_status(status_code: int) -> bool:
    return status_code in (429, 500, 502, 503, 504)


class NemotronClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = DEFAULT_NVIDIA_MODEL,
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        clean_model = model.strip() if isinstance(model, str) else ""
        if not clean_model or clean_model.lower() in ("llm", "nvidia", "default", "none"):
            clean_model = DEFAULT_NVIDIA_MODEL
        self.model = clean_model
        self.timeout = timeout
        self.temperature = temperature
        self.last_call_meta: dict[str, Any] = {
            "retries": 0,
            "fallback_used": False,
            "effective_model": self.model,
        }

    def validate_config(self) -> None:
        if not self.api_key:
            raise NemotronConnectionError("NVIDIA_API_KEY is not configured or empty.")

    def _candidate_models(self) -> list[str]:
        ordered = [self.model]
        for fb in FALLBACK_NVIDIA_MODELS:
            if fb not in ordered:
                ordered.append(fb)
        healthy = [m for m in ordered if not _is_model_in_cooldown(m)]
        cooled = [m for m in ordered if _is_model_in_cooldown(m)]
        return healthy + cooled

    @staticmethod
    def _is_thinking_capable(model_name: str) -> bool:
        low = model_name.lower()
        return any(
            marker in low
            for marker in ("nemotron-3.5-super", "nemotron-3.5-lightning", "nemotron-3-ultra", "reasoning")
        )

    def _build_chat_payload(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        json_format: bool = False,
        temperature: float | None = None,
        max_tokens: int = 4096,
        enable_thinking: bool = True,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if json_format:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if not enable_thinking and self._is_thinking_capable(model_name):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        models_url = f"{self.base_url}/models"
        try:
            if is_urlopen_patched():
                req = urllib.request.Request(
                    models_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=min(5.0, self.timeout)) as resp:  # nosec B310
                    return resp.status == 200
            client = get_shared_sync_http_client(read_timeout=min(5.0, self.timeout))
            resp = client.get(
                models_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=min(5.0, self.timeout),
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Nemotron availability check failed: %s", exc)
            return False

    def list_models(self) -> list[str]:
        if not self.api_key:
            return []
        models_url = f"{self.base_url}/models"
        try:
            if is_urlopen_patched():
                req = urllib.request.Request(
                    models_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=min(6.0, self.timeout)) as resp:  # nosec B310
                    data = json.loads(resp.read().decode("utf-8"))
            else:
                client = get_shared_sync_http_client(read_timeout=min(6.0, self.timeout))
                resp = client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=min(6.0, self.timeout),
                )
                resp.raise_for_status()
                data = resp.json()

            models = data.get("data", [])
            chat_models = []
            for m in models:
                mid = str(m.get("id", ""))
                low = mid.lower()
                if "nemotron" not in low:
                    continue
                if any(bad in low for bad in _NON_CHAT_MODEL_KEYWORDS):
                    continue
                chat_models.append(mid)
            return chat_models or [self.model]
        except Exception as exc:
            logger.warning("Could not list Nemotron models: %s", exc)
            return [self.model]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_format: bool = True,
        temperature: float | None = None,
        enable_thinking: bool = True,
    ) -> str:
        self.validate_config()
        chat_url = f"{self.base_url}/chat/completions"

        if is_urlopen_patched():
            payload = self._build_chat_payload(
                self.model,
                messages,
                stream=False,
                json_format=json_format,
                temperature=temperature,
                enable_thinking=enable_thinking,
            )
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
                        return ""
                    return choices[0].get("message", {}).get("content", "") or ""
            except TimeoutError as exc:
                raise NemotronTimeoutError(
                    f"Request to NVIDIA NIM timed out after {self.timeout}s"
                ) from exc
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise NemotronResponseError(
                    f"NVIDIA HTTP {exc.code}: {exc.reason} - {err_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise NemotronConnectionError(
                    f"Cannot connect to NVIDIA NIM at {chat_url}: {exc.reason}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise NemotronResponseError(
                    f"Invalid JSON returned from NVIDIA NIM: {exc}"
                ) from exc

        candidates = self._candidate_models()
        retries = 0
        last_exc: Exception | None = None
        client = get_shared_sync_http_client(read_timeout=self.timeout)

        for idx, candidate_model in enumerate(candidates):
            is_fallback = idx > 0
            # Keep TTFT/read cap reasonable on primary stalled models so fallback completes quickly
            model_timeout = min(15.0, self.timeout) if (idx == 0 and len(candidates) > 1 and "ultra-550b" in candidate_model) else self.timeout
            payload = self._build_chat_payload(
                candidate_model,
                messages,
                stream=False,
                json_format=json_format,
                temperature=temperature,
                enable_thinking=enable_thinking,
            )

            max_attempts = 2 if idx == 0 else 1
            for attempt in range(max_attempts):
                try:
                    resp = client.post(
                        chat_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=httpx.Timeout(
                            connect=5.0,
                            read=model_timeout,
                            write=10.0,
                            pool=5.0,
                        ),
                    )
                    if resp.status_code >= 400:
                        err_body = resp.text
                        if _is_non_retryable_status(resp.status_code):
                            raise NemotronResponseError(
                                f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                            )
                        if _is_transient_status(resp.status_code) and attempt + 1 < max_attempts:
                            retries += 1
                            time.sleep(0.25 + random.uniform(0.05, 0.2))
                            continue
                        if _is_model_fallback_status(resp.status_code) and idx + 1 < len(candidates):
                            retries += 1
                            _mark_model_unhealthy(candidate_model)
                            last_exc = NemotronResponseError(
                                f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                            )
                            logger.warning(
                                "Model %s returned HTTP %d; falling back to next healthy model.",
                                candidate_model,
                                resp.status_code,
                            )
                            break
                        raise NemotronResponseError(
                            f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                        )

                    data = resp.json()
                    choices = data.get("choices", [])
                    self.last_call_meta = {
                        "retries": retries,
                        "fallback_used": is_fallback,
                        "effective_model": candidate_model,
                    }
                    if not choices:
                        return ""
                    msg = choices[0].get("message", {}) or {}
                    return msg.get("content") or ""
                except NemotronResponseError:
                    raise
                except httpx.TimeoutException as exc:
                    last_exc = NemotronTimeoutError(
                        f"Request to NVIDIA NIM timed out after {model_timeout}s"
                    )
                    if idx + 1 < len(candidates):
                        retries += 1
                        _mark_model_unhealthy(candidate_model)
                        logger.warning(
                            "Model %s timed out after %.1fs; falling back to next candidate.",
                            candidate_model,
                            model_timeout,
                        )
                        break
                    raise last_exc from exc
                except httpx.ConnectError as exc:
                    last_exc = NemotronConnectionError(
                        f"Cannot connect to NVIDIA NIM at {chat_url}: {exc}"
                    )
                    if attempt + 1 < max_attempts:
                        retries += 1
                        time.sleep(0.25 + random.uniform(0.05, 0.2))
                        continue
                    raise last_exc from exc
                except json.JSONDecodeError as exc:
                    raise NemotronResponseError(
                        f"Invalid JSON returned from NVIDIA NIM: {exc}"
                    ) from exc

        if last_exc:
            raise last_exc
        raise NemotronTimeoutError(f"Request to NVIDIA NIM timed out after {self.timeout}s")

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
        enable_thinking: bool = True,
    ) -> Iterator[str]:
        self.validate_config()
        chat_url = f"{self.base_url}/chat/completions"

        if is_urlopen_patched():
            payload = self._build_chat_payload(
                self.model,
                messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            )
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
                return
            except TimeoutError as exc:
                raise NemotronTimeoutError(
                    f"Request to NVIDIA NIM timed out after {self.timeout}s"
                ) from exc
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise NemotronResponseError(
                    f"NVIDIA HTTP {exc.code}: {exc.reason} - {err_body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise NemotronConnectionError(
                    f"Cannot connect to NVIDIA NIM at {chat_url}: {exc.reason}"
                ) from exc

        candidates = self._candidate_models()
        retries = 0
        last_exc: Exception | None = None
        client = get_shared_sync_http_client(read_timeout=self.timeout)

        for idx, candidate_model in enumerate(candidates):
            is_fallback = idx > 0
            ttft_cap = 12.0 if (idx == 0 and len(candidates) > 1 and "ultra-550b" in candidate_model) else min(20.0, self.timeout)
            payload = self._build_chat_payload(
                candidate_model,
                messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            )
            emitted_any = False
            try:
                with client.stream(
                    "POST",
                    chat_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=httpx.Timeout(
                        connect=5.0,
                        read=max(ttft_cap, 25.0),
                        write=10.0,
                        pool=5.0,
                    ),
                ) as resp:
                    if resp.status_code >= 400:
                        err_body = resp.read().decode("utf-8", errors="replace")
                        if _is_non_retryable_status(resp.status_code):
                            raise NemotronResponseError(
                                f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                            )
                        if _is_model_fallback_status(resp.status_code) and idx + 1 < len(candidates):
                            retries += 1
                            _mark_model_unhealthy(candidate_model)
                            last_exc = NemotronResponseError(
                                f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                            )
                            logger.warning(
                                "Streaming model %s failed HTTP %d; falling back.",
                                candidate_model,
                                resp.status_code,
                            )
                            continue
                        raise NemotronResponseError(
                            f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                        )

                    self.last_call_meta = {
                        "retries": retries,
                        "fallback_used": is_fallback,
                        "effective_model": candidate_model,
                    }
                    stream_start = time.monotonic()
                    for line_str in resp.iter_lines():
                        if not emitted_any and (time.monotonic() - stream_start) > ttft_cap:
                            raise httpx.ReadTimeout(
                                f"Model {candidate_model} produced no content within {ttft_cap:.1f}s TTFT budget"
                            )
                        clean = line_str.strip()
                        if not clean or clean.startswith(":"):
                            continue
                        if clean == "data: [DONE]":
                            break
                        if clean.startswith("data: "):
                            json_str = clean[6:].strip()
                            if not json_str:
                                continue
                            try:
                                data = json.loads(json_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {}) or {}
                                    content = delta.get("content", "")
                                    if content:
                                        emitted_any = True
                                        yield content
                            except json.JSONDecodeError:
                                continue
                    return
            except NemotronResponseError:
                raise
            except httpx.TimeoutException as exc:
                last_exc = NemotronTimeoutError(
                    f"Request to NVIDIA NIM timed out after {ttft_cap}s"
                )
                if not emitted_any and idx + 1 < len(candidates):
                    retries += 1
                    _mark_model_unhealthy(candidate_model)
                    logger.warning(
                        "Streaming model %s timed out before first token (%.1fs); falling back.",
                        candidate_model,
                        ttft_cap,
                    )
                    continue
                raise last_exc from exc
            except httpx.ConnectError as exc:
                last_exc = NemotronConnectionError(
                    f"Cannot connect to NVIDIA NIM at {chat_url}: {exc}"
                )
                if not emitted_any and idx + 1 < len(candidates):
                    retries += 1
                    _mark_model_unhealthy(candidate_model)
                    continue
                raise last_exc from exc

        if last_exc:
            raise last_exc

    async def astream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
        enable_thinking: bool = True,
        ttft_timeout: float = 15.0,
        idle_timeout: float = 25.0,
    ) -> AsyncIterator[str]:
        """True async non-blocking SSE stream with connect/TTFT/idle timeouts and pre-token fallback."""
        self.validate_config()
        chat_url = f"{self.base_url}/chat/completions"
        candidates = self._candidate_models()
        retries = 0
        last_exc: Exception | None = None

        for idx, candidate_model in enumerate(candidates):
            is_fallback = idx > 0
            # Fast-fail ultra-550b stall at 12s when fallback is available
            active_ttft = (
                min(12.0, ttft_timeout)
                if (idx == 0 and len(candidates) > 1 and "ultra-550b" in candidate_model)
                else ttft_timeout
            )
            payload = self._build_chat_payload(
                candidate_model,
                messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            )
            client = get_loop_async_http_client(
                connect_timeout=5.0,
                read_timeout=max(active_ttft, idle_timeout),
            )
            emitted_any = False

            max_attempts = 2 if idx == 0 else 1
            for attempt in range(max_attempts):
                try:
                    async with client.stream(
                        "POST",
                        chat_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=httpx.Timeout(
                            connect=5.0,
                            read=active_ttft if not emitted_any else idle_timeout,
                            write=10.0,
                            pool=5.0,
                        ),
                    ) as resp:
                        if resp.status_code >= 400:
                            err_body = (await resp.aread()).decode("utf-8", errors="replace")
                            if _is_non_retryable_status(resp.status_code):
                                raise NemotronResponseError(
                                    f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                                )
                            if _is_transient_status(resp.status_code) and attempt + 1 < max_attempts:
                                retries += 1
                                await asyncio.sleep(0.25 + random.uniform(0.05, 0.2))
                                continue
                            if _is_model_fallback_status(resp.status_code) and idx + 1 < len(candidates):
                                retries += 1
                                _mark_model_unhealthy(candidate_model)
                                last_exc = NemotronResponseError(
                                    f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                                )
                                logger.warning(
                                    "Async model %s HTTP %d; falling back to next candidate.",
                                    candidate_model,
                                    resp.status_code,
                                )
                                break
                            raise NemotronResponseError(
                                f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {err_body}"
                            )

                        self.last_call_meta = {
                            "retries": retries,
                            "fallback_used": is_fallback,
                            "effective_model": candidate_model,
                        }

                        line_iter = resp.aiter_lines().__aiter__()
                        stream_start = time.monotonic()
                        while True:
                            if not emitted_any:
                                remaining_ttft = active_ttft - (time.monotonic() - stream_start)
                                if remaining_ttft <= 0:
                                    raise httpx.ReadTimeout(
                                        f"Model {candidate_model} produced no content within {active_ttft:.1f}s TTFT budget"
                                    )
                                step_timeout = min(active_ttft, remaining_ttft)
                            else:
                                step_timeout = idle_timeout
                            try:
                                line_str = await asyncio.wait_for(
                                    line_iter.__anext__(), timeout=step_timeout
                                )
                            except StopAsyncIteration:
                                break
                            except TimeoutError as t_exc:
                                raise httpx.ReadTimeout(
                                    f"Stream timed out waiting for {'first token' if not emitted_any else 'next chunk'} after {step_timeout:.1f}s"
                                ) from t_exc

                            clean = line_str.strip()
                            if not clean or clean.startswith(":"):
                                continue
                            if clean == "data: [DONE]":
                                break
                            if clean.startswith("data: "):
                                json_str = clean[6:].strip()
                                if not json_str:
                                    continue
                                try:
                                    data = json.loads(json_str)
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {}) or {}
                                        content = delta.get("content", "")
                                        if content:
                                            emitted_any = True
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                        return
                except NemotronResponseError:
                    raise
                except httpx.TimeoutException as exc:
                    last_exc = NemotronTimeoutError(
                        f"Request to NVIDIA NIM timed out after {active_ttft}s"
                    )
                    if not emitted_any:
                        if idx + 1 < len(candidates):
                            retries += 1
                            _mark_model_unhealthy(candidate_model)
                            logger.warning(
                                "Async model %s stalled/timed out at %.1fs before first token; falling back to next candidate.",
                                candidate_model,
                                active_ttft,
                            )
                            break
                        raise last_exc from exc
                    raise NemotronResponseError(
                        "The response stream was interrupted mid-generation."
                    ) from exc
                except httpx.ConnectError as exc:
                    last_exc = NemotronConnectionError(
                        f"Cannot connect to NVIDIA NIM at {chat_url}: {exc}"
                    )
                    if not emitted_any and attempt + 1 < max_attempts:
                        retries += 1
                        await asyncio.sleep(0.25 + random.uniform(0.05, 0.2))
                        continue
                    if not emitted_any and idx + 1 < len(candidates):
                        retries += 1
                        _mark_model_unhealthy(candidate_model)
                        break
                    raise last_exc from exc

        if last_exc:
            raise last_exc
        raise NemotronTimeoutError(f"Request to NVIDIA NIM timed out after {self.timeout}s")

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Execute a chat completion with OpenAI-style tool definitions and parse tool calls."""
        self.validate_config()
        chat_url = f"{self.base_url}/chat/completions"

        def _parse_response_data(data: dict[str, Any]) -> dict[str, Any]:
            choices = data.get("choices", [])
            if not choices:
                return {"content": "", "tool_calls": []}
            msg = choices[0].get("message", {}) or {}
            raw_calls = msg.get("tool_calls") or []
            parsed_calls: list[dict[str, Any]] = []
            for tc in raw_calls:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments", "{}")
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

        if is_urlopen_patched():
            payload = self._build_chat_payload(
                self.model,
                messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
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
                    return _parse_response_data(data)
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

        candidates = self._candidate_models()
        client = get_shared_sync_http_client(read_timeout=self.timeout)
        last_exc: Exception | None = None

        for idx, candidate_model in enumerate(candidates):
            model_timeout = min(15.0, self.timeout) if (idx == 0 and len(candidates) > 1 and "ultra-550b" in candidate_model) else self.timeout
            payload = self._build_chat_payload(
                candidate_model,
                messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
            try:
                resp = client.post(
                    chat_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=httpx.Timeout(connect=5.0, read=model_timeout, write=10.0, pool=5.0),
                )
                if resp.status_code in (400, 404, 422) and tools and "tool" in resp.text.lower():
                    logger.warning(
                        "Model rejected native tools (%s); falling back to prompt adapter.",
                        resp.status_code,
                    )
                    return self._fallback_prompt_tool_call(messages, tools, temperature=temperature)
                if resp.status_code >= 400:
                    if _is_model_fallback_status(resp.status_code) and idx + 1 < len(candidates):
                        _mark_model_unhealthy(candidate_model)
                        last_exc = NemotronResponseError(
                            f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {resp.text}"
                        )
                        continue
                    raise NemotronResponseError(
                        f"NVIDIA HTTP {resp.status_code}: {resp.reason_phrase} - {resp.text}"
                    )
                self.last_call_meta = {
                    "retries": idx,
                    "fallback_used": idx > 0,
                    "effective_model": candidate_model,
                }
                return _parse_response_data(resp.json())
            except httpx.TimeoutException as exc:
                last_exc = NemotronTimeoutError(
                    f"Request to NVIDIA NIM timed out after {model_timeout}s"
                )
                if idx + 1 < len(candidates):
                    _mark_model_unhealthy(candidate_model)
                    continue
                raise last_exc from exc
            except httpx.ConnectError as exc:
                raise NemotronConnectionError(
                    f"Cannot connect to NVIDIA NIM at {chat_url}: {exc}"
                ) from exc

        if last_exc:
            raise last_exc
        raise NemotronTimeoutError(f"Request to NVIDIA NIM timed out after {self.timeout}s")

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
