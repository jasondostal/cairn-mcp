"""Test LLM factory: registration, routing, error handling, and live provider smoke tests."""

import os
import pytest

from cairn.config import LLMConfig
from cairn.llm import get_llm, register_llm_provider, _providers, BUILT_IN_PROVIDERS
from cairn.llm.interface import LLMInterface
from tests.helpers import MockLLM


class StubLLM(LLMInterface):
    """Minimal stub for factory registration tests."""

    def generate(self, messages, max_tokens=1024):
        return "stub-response"

    def get_model_name(self):
        return "stub"

    def get_context_size(self):
        return 999


# ── Factory routing ──────────────────────────────────────────


def test_factory_routes_ollama():
    """Factory should resolve 'ollama' to OllamaLLM (import check only)."""
    from cairn.llm.ollama import OllamaLLM

    cfg = LLMConfig(backend="ollama")
    llm = get_llm(cfg)
    assert isinstance(llm, OllamaLLM)


def test_factory_routes_gemini_requires_key():
    """Gemini backend should raise if no API key is set."""
    cfg = LLMConfig(backend="gemini", gemini_api_key="")
    with pytest.raises(ValueError, match="CAIRN_GEMINI_API_KEY"):
        get_llm(cfg)


def test_factory_routes_openai_requires_key():
    """OpenAI backend should raise if no API key is set."""
    cfg = LLMConfig(backend="openai", openai_api_key="")
    with pytest.raises(ValueError, match="CAIRN_OPENAI_API_KEY"):
        get_llm(cfg)


def test_factory_unknown_backend():
    """Unknown backend should raise ValueError with available list."""
    cfg = LLMConfig(backend="does-not-exist")
    with pytest.raises(ValueError, match="does-not-exist"):
        get_llm(cfg)


# ── Registry ─────────────────────────────────────────────────


def test_register_and_retrieve():
    """Registered provider should be returned by get_llm."""
    register_llm_provider("test-stub", lambda cfg: StubLLM())
    try:
        cfg = LLMConfig(backend="test-stub")
        llm = get_llm(cfg)
        assert isinstance(llm, StubLLM)
        assert llm.generate([]) == "stub-response"
    finally:
        _providers.pop("test-stub", None)


def test_registry_overrides_builtin():
    """A registered provider with a built-in name should take priority."""
    register_llm_provider("ollama", lambda cfg: StubLLM())
    try:
        cfg = LLMConfig(backend="ollama")
        llm = get_llm(cfg)
        assert isinstance(llm, StubLLM)  # Registry wins, not OllamaLLM
    finally:
        _providers.pop("ollama", None)


def test_built_in_providers_list():
    """All four built-in backends should be listed."""
    assert "ollama" in BUILT_IN_PROVIDERS
    assert "bedrock" in BUILT_IN_PROVIDERS
    assert "gemini" in BUILT_IN_PROVIDERS
    assert "openai" in BUILT_IN_PROVIDERS


# ── Live Gemini smoke test ───────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("CAIRN_GEMINI_API_KEY"),
    reason="CAIRN_GEMINI_API_KEY not set — skipping live Gemini test",
)
def test_gemini_live():
    """Smoke test: send a real prompt to Gemini and get a response."""
    cfg = LLMConfig(
        backend="gemini",
        gemini_api_key=os.getenv("CAIRN_GEMINI_API_KEY"),
        gemini_model=os.getenv("CAIRN_GEMINI_MODEL", "gemini-2.0-flash"),
    )
    llm = get_llm(cfg)

    response = llm.generate([
        {"role": "system", "content": "You are a helpful assistant. Respond in one sentence."},
        {"role": "user", "content": "What is 2 + 2?"},
    ], max_tokens=50)

    assert response is not None
    assert len(response) > 0
    assert "4" in response
    print(f"\nGemini live response: {response}")


# ── Live OpenAI-compat smoke test ────────────────────────────


@pytest.mark.skipif(
    not os.getenv("CAIRN_OPENAI_API_KEY"),
    reason="CAIRN_OPENAI_API_KEY not set — skipping live OpenAI test",
)
def test_openai_live():
    """Smoke test: send a real prompt to an OpenAI-compatible endpoint."""
    cfg = LLMConfig(
        backend="openai",
        openai_api_key=os.getenv("CAIRN_OPENAI_API_KEY"),
        openai_base_url=os.getenv("CAIRN_OPENAI_BASE_URL", "https://api.openai.com"),
        openai_model=os.getenv("CAIRN_OPENAI_MODEL", "gpt-4o-mini"),
    )
    llm = get_llm(cfg)

    response = llm.generate([
        {"role": "system", "content": "You are a helpful assistant. Respond in one sentence."},
        {"role": "user", "content": "What is 2 + 2?"},
    ], max_tokens=50)

    assert response is not None
    assert len(response) > 0
    assert "4" in response
    print(f"\nOpenAI-compat live response: {response}")
