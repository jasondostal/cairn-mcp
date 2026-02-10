"""LLM backend factory with pluggable provider registry.

Built-in providers: ollama, bedrock, gemini, openai.
Register custom providers via ``register_llm_provider(name, factory_fn)``.
"""

from __future__ import annotations

import logging
from typing import Callable

from cairn.config import LLMConfig
from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Provider registry: name -> factory function(config) -> LLMInterface
_providers: dict[str, Callable[[LLMConfig], LLMInterface]] = {}


def register_llm_provider(
    name: str,
    factory: Callable[[LLMConfig], LLMInterface],
) -> None:
    """Register a custom LLM provider.

    Args:
        name: Backend name (matches CAIRN_LLM_BACKEND env var).
        factory: Callable that takes LLMConfig and returns an LLMInterface.

    Example::

        from cairn.llm import register_llm_provider
        from cairn.llm.interface import LLMInterface

        class MyLLM(LLMInterface):
            ...

        register_llm_provider("my-backend", lambda cfg: MyLLM(cfg))
    """
    _providers[name] = factory
    logger.info("Registered LLM provider: %s", name)


def get_llm(config: LLMConfig) -> LLMInterface:
    """Return the configured LLM backend.

    Checks the plugin registry first, then falls back to built-in providers.
    """
    # Check plugin registry
    if config.backend in _providers:
        return _providers[config.backend](config)

    # Built-in providers (lazy imports to avoid heavy deps at module load)
    if config.backend == "bedrock":
        from cairn.llm.bedrock import BedrockLLM
        return BedrockLLM(config)
    elif config.backend == "ollama":
        from cairn.llm.ollama import OllamaLLM
        return OllamaLLM(config)
    elif config.backend == "gemini":
        from cairn.llm.gemini import GeminiLLM
        return GeminiLLM(config)
    elif config.backend == "openai":
        from cairn.llm.openai_compat import OpenAICompatibleLLM
        return OpenAICompatibleLLM(config)
    else:
        available = sorted(set(BUILT_IN_PROVIDERS + list(_providers.keys())))
        raise ValueError(
            f"Unknown LLM backend: {config.backend!r}. "
            f"Available: {', '.join(available)}"
        )


# For error messages and discovery
BUILT_IN_PROVIDERS = ["ollama", "bedrock", "gemini", "openai"]
