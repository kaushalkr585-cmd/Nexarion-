import logging
import time

from fastapi import APIRouter

from code_review.config import get_settings
from code_review.llm.client import OllamaClient
from code_review.llm.nemotron_client import NemotronClient
from code_review.web.schemas import (
    ProviderStatusItem,
    ProviderStatusResponse,
    ProviderTestRequest,
    ProviderTestResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/providers", tags=["Providers"])


@router.get("/status", response_model=ProviderStatusResponse)
def get_providers_status() -> ProviderStatusResponse:
    settings = get_settings()

    ollama = OllamaClient(
        base_url=settings.ollama_base_url or settings.llm_base_url,
        model=settings.ollama_model or settings.llm_model,
        timeout=3.0,
    )
    ollama_ok = ollama.is_available()

    nemotron = NemotronClient(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=settings.nvidia_model,
        timeout=5.0,
    )
    nemotron_ok = nemotron.is_available()

    ollama_models: list[str] = []
    if ollama_ok:
        try:
            ollama_models = ollama.list_models()
        except Exception:
            ollama_models = []
    if not ollama_models and settings.ollama_model:
        ollama_models = [settings.ollama_model]

    nemotron_models: list[str] = []
    if nemotron_ok:
        try:
            discovered = nemotron.list_models()
            nemotron_models = discovered[:6] if discovered else []
        except Exception:
            nemotron_models = []
    if settings.nvidia_model and settings.nvidia_model not in nemotron_models:
        nemotron_models.insert(0, settings.nvidia_model)

    providers = [
        ProviderStatusItem(
            provider="llm",
            name="LLM (Cloud)",
            is_available=nemotron_ok,
            current_model=settings.nvidia_model,
            endpoint=settings.nvidia_base_url,
            type="cloud",
            note="High-reasoning cloud inference via LLM"
            if nemotron_ok
            else "API key missing or invalid",
            available_models=nemotron_models,
        ),
        ProviderStatusItem(
            provider="ollama",
            name="Ollama (Local)",
            is_available=False,
            current_model=settings.ollama_model or settings.llm_model,
            endpoint=settings.ollama_base_url or settings.llm_base_url,
            type="local",
            note="Disabled for cloud deployment (Nemotron exclusive)",
            available_models=[],
        ),
    ]

    return ProviderStatusResponse(
        active_provider="llm",
        providers=providers,
    )


@router.post("/test", response_model=ProviderTestResponse)
def test_provider(payload: ProviderTestRequest) -> ProviderTestResponse:
    settings = get_settings()
    provider = payload.provider.lower().strip()

    start_time = time.perf_counter()

    if provider in ("nvidia", "llm"):
        api_key = payload.api_key or settings.nvidia_api_key
        client = NemotronClient(
            api_key=api_key,
            base_url=settings.nvidia_base_url,
            model=payload.model or settings.nvidia_model,
            timeout=10.0,
        )
        try:
            available = client.is_available()
            latency = round((time.perf_counter() - start_time) * 1000, 1)
            if available:
                models = client.list_models()
                return ProviderTestResponse(
                    provider="llm",
                    success=True,
                    message=f"Successfully connected to LLM ({latency}ms).",
                    latency_ms=latency,
                    models=models,
                )
            return ProviderTestResponse(
                provider="llm",
                success=False,
                message="LLM endpoint unreachable or API key invalid.",
                latency_ms=latency,
            )
        except Exception as exc:
            return ProviderTestResponse(
                provider="llm",
                success=False,
                message=f"Connection error: {exc}",
            )

    client_ollama = OllamaClient(
        base_url=settings.ollama_base_url or settings.llm_base_url,
        model=payload.model or settings.ollama_model or settings.llm_model,
        timeout=4.0,
    )
    try:
        available = client_ollama.is_available()
        latency = round((time.perf_counter() - start_time) * 1000, 1)
        if available:
            models = client_ollama.list_models()
            return ProviderTestResponse(
                provider="ollama",
                success=True,
                message=f"Successfully connected to local Ollama ({latency}ms).",
                latency_ms=latency,
                models=models,
            )
        return ProviderTestResponse(
            provider="ollama",
            success=False,
            message="Local Ollama server is not running on localhost:11434.",
            latency_ms=latency,
        )
    except Exception as exc:
        return ProviderTestResponse(
            provider="ollama",
            success=False,
            message=f"Connection error: {exc}",
        )
