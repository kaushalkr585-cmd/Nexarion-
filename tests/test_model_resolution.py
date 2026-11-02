"""Tests verifying model parameter resolution and normalization across providers."""
from code_review.config import get_settings
from code_review.llm.factory import get_llm_client
from code_review.llm.nemotron_client import NemotronClient
from code_review.llm.client import OllamaClient


def test_get_llm_client_normalizes_dummy_model_names():
    settings = get_settings()

    # When client sends "llm" as the model name
    client_llm = get_llm_client(provider="llm", model="llm")
    assert isinstance(client_llm, NemotronClient)
    assert client_llm.model == settings.nvidia_model
    assert client_llm.model != "llm"

    # When client sends "nvidia" as the model name
    client_nvidia = get_llm_client(provider="nvidia", model="nvidia")
    assert isinstance(client_nvidia, NemotronClient)
    assert client_nvidia.model == settings.nvidia_model
    assert client_nvidia.model != "nvidia"

    # When client sends "default" as the model name
    client_default = get_llm_client(provider="llm", model="default")
    assert client_default.model == settings.nvidia_model

    # When client sends None or empty string
    client_none = get_llm_client(provider="llm", model=None)
    assert client_none.model == settings.nvidia_model

    client_empty = get_llm_client(provider="llm", model="   ")
    assert client_empty.model == settings.nvidia_model

    # Ollama provider normalization
    client_ollama = get_llm_client(provider="ollama", model="ollama")
    assert isinstance(client_ollama, OllamaClient)
    expected_ollama = settings.ollama_model or settings.llm_model
    assert client_ollama.model == expected_ollama


def test_nemotron_client_guard():
    # Direct instantiation with dummy strings
    client = NemotronClient(model="llm")
    assert client.model == "nvidia/nemotron-3-ultra-550b-a55b"

    client2 = NemotronClient(model="nvidia")
    assert client2.model == "nvidia/nemotron-3-ultra-550b-a55b"

    client3 = NemotronClient(model="")
    assert client3.model == "nvidia/nemotron-3-ultra-550b-a55b"

