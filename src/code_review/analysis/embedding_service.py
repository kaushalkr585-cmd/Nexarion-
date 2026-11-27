from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
import numpy as np

from code_review.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_NVIDIA_EMBED_MODEL = "nvidia/nemotron-3.5-embed-1b"

_EMBED_HTTP_LOCK = threading.Lock()
_EMBED_HTTP_CLIENT: httpx.Client | None = None


def _get_embed_http_client(timeout: float) -> httpx.Client:
    global _EMBED_HTTP_CLIENT
    with _EMBED_HTTP_LOCK:
        if _EMBED_HTTP_CLIENT is None or _EMBED_HTTP_CLIENT.is_closed:
            _EMBED_HTTP_CLIENT = httpx.Client(
                timeout=httpx.Timeout(connect=2.5, read=timeout, write=3.0, pool=2.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return _EMBED_HTTP_CLIENT


def compute_cosine_similarity(
    vec_a: list[float] | np.ndarray | None,
    vec_b: list[float] | np.ndarray | None,
) -> float:
    if vec_a is None or vec_b is None:
        return 0.0
    try:
        a = np.asarray(vec_a, dtype=np.float32)
        b = np.asarray(vec_b, dtype=np.float32)
        if a.size == 0 or b.size == 0 or a.shape != b.shape:
            return 0.0
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a <= 1e-9 or norm_b <= 1e-9:
            return 0.0
        similarity = float(np.dot(a, b) / (norm_a * norm_b))
        return max(-1.0, min(1.0, similarity))
    except Exception as exc:
        logger.debug("Cosine similarity calculation error: %s", exc)
        return 0.0


class EmbeddingService:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        timeout: float = 4.0,
    ) -> None:
        settings = get_settings()
        self.provider = (provider or settings.embedding_provider or "auto").lower().strip()
        self.model = model or settings.embedding_model or "nomic-embed-text"
        self.timeout = timeout
        self.settings = settings
        self._cache: dict[str, list[float]] = {}
        self._failure_cooldown_until: dict[str, float] = {}

    def get_embedding(
        self,
        text: str,
        *,
        input_type: str = "passage",
    ) -> list[float] | None:
        clean_text = text.strip()
        if not clean_text or self.provider == "none":
            return None

        effective_provider = self._resolve_provider()
        cooldown_until = self._failure_cooldown_until.get(effective_provider, 0.0)
        if time.monotonic() < cooldown_until:
            return None

        cache_key = f"{effective_provider}:{self.model}:{input_type}:{hash(clean_text)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        embedding: list[float] | None = None
        if effective_provider in ("nvidia", "llm"):
            embedding = self._embed_nvidia(clean_text, input_type=input_type)
        elif effective_provider == "ollama":
            embedding = self._embed_ollama(clean_text)

        if embedding:
            if len(self._cache) > 2000:
                self._cache.clear()
            self._cache[cache_key] = embedding
        else:
            # Circuit breaker: pause repeated remote embedding calls for 60s on failure
            self._failure_cooldown_until[effective_provider] = time.monotonic() + 60.0

        return embedding

    def _resolve_provider(self) -> str:
        if self.provider in ("ollama", "nvidia", "llm"):
            return "nvidia" if self.provider == "llm" else self.provider

        active_llm_provider = (self.settings.llm_provider or "llm").lower().strip()
        if active_llm_provider in ("nvidia", "llm") and self.settings.nvidia_api_key:
            return "nvidia"
        return "ollama"

    def _embed_ollama(self, text: str) -> list[float] | None:
        base_url = (self.settings.ollama_base_url or "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/embeddings"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": text,
        }

        try:
            client = _get_embed_http_client(self.timeout)
            resp = client.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                vec = data.get("embedding")
                if isinstance(vec, list) and vec:
                    return [float(x) for x in vec]
            elif resp.status_code == 404:
                alt_url = f"{base_url}/api/embed"
                alt_resp = client.post(
                    alt_url,
                    json={"model": self.model, "input": text},
                    timeout=self.timeout,
                )
                if alt_resp.status_code == 200:
                    data = alt_resp.json()
                    embeddings = data.get("embeddings")
                    if isinstance(embeddings, list) and len(embeddings) > 0:
                        return [float(x) for x in embeddings[0]]
        except Exception as exc:
            logger.debug("Ollama embedding service unavailable: %s", exc)

        return None

    def _embed_nvidia(self, text: str, *, input_type: str = "passage") -> list[float] | None:
        api_key = self.settings.nvidia_api_key
        if not api_key:
            return None

        base_url = (self.settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1").rstrip(
            "/"
        )
        url = f"{base_url}/v1/embeddings" if not base_url.endswith("/v1") else f"{base_url}/embeddings"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Avoid deprecated nvidia/llama-3.2-nv-embedqa-1b-v2 (EOL 2026-05-18 -> HTTP 410)
        if "nv-embedqa-1b-v2" in self.model:
            model_name = DEFAULT_NVIDIA_EMBED_MODEL
        elif "nv-embed" in self.model or "nemotron-3.5-embed" in self.model or "embedding" in self.model:
            model_name = self.model
        else:
            model_name = DEFAULT_NVIDIA_EMBED_MODEL

        payload: dict[str, Any] = {
            "input": [text],
            "model": model_name,
            "encoding_format": "float",
        }
        if "nemotron-3.5-embed" in model_name or "nv-embedqa" in model_name:
            payload["input_type"] = "query" if input_type == "query" else "passage"

        try:
            client = _get_embed_http_client(self.timeout)
            resp = client.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data")
                if isinstance(items, list) and len(items) > 0:
                    vec = items[0].get("embedding")
                    if isinstance(vec, list):
                        return [float(x) for x in vec]
            else:
                logger.debug(
                    "NVIDIA embedding non-200 status=%d model=%s", resp.status_code, model_name
                )
        except Exception as exc:
            logger.debug("NVIDIA embedding service error: %s", exc)

        return None


_global_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _global_embedding_service
    if _global_embedding_service is None:
        _global_embedding_service = EmbeddingService()
    return _global_embedding_service
