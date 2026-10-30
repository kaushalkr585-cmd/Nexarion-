from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from code_review.config import get_settings
from code_review.llm.client import OllamaClient
from code_review.llm.nemotron_client import NemotronClient

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClientProtocol(Protocol):
    def is_available(self) -> bool:
        ...

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_format: bool = True,
        temperature: float | None = None,
    ) -> str:
        ...

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> Iterator[str]:
        ...


def get_llm_client(
    provider: str | None = None,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
) -> LLMClientProtocol:
    settings = get_settings()
    active_provider = (provider or settings.llm_provider or "ollama").lower().strip()
    timeout_val = timeout if timeout is not None else settings.llm_timeout_seconds
    temp_val = temperature if temperature is not None else settings.llm_temperature

    if active_provider == "nvidia":
        key = api_key or settings.nvidia_api_key
        url = base_url or settings.nvidia_base_url
        mdl = model or settings.nvidia_model
        logger.info("Initializing NemotronClient (model: %s, url: %s)", mdl, url)
        return NemotronClient(
            api_key=key,
            base_url=url,
            model=mdl,
            timeout=timeout_val,
            temperature=temp_val,
        )

    url = base_url or settings.ollama_base_url or settings.llm_base_url
    mdl = model or settings.ollama_model or settings.llm_model
    logger.info("Initializing OllamaClient (model: %s, url: %s)", mdl, url)
    return OllamaClient(
        base_url=url,
        model=mdl,
        timeout=timeout_val,
        temperature=temp_val,
    )
