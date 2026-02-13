"""Reranker backend factory with pluggable provider registry.

Built-in providers: local (cross-encoder), bedrock (AWS Bedrock Rerank API).
Register custom providers via ``register_reranker_provider(name, factory_fn)``.
"""

from __future__ import annotations

import logging
from typing import Callable

from cairn.config import RerankerConfig
from cairn.core.reranker.interface import RerankerInterface

logger = logging.getLogger(__name__)

# Provider registry: name -> factory function(config) -> RerankerInterface
_providers: dict[str, Callable[[RerankerConfig], RerankerInterface]] = {}


def register_reranker_provider(
    name: str,
    factory: Callable[[RerankerConfig], RerankerInterface],
) -> None:
    """Register a custom reranker provider.

    Args:
        name: Backend name (matches CAIRN_RERANKER_BACKEND env var).
        factory: Callable that takes RerankerConfig and returns a RerankerInterface.

    Example::

        from cairn.core.reranker import register_reranker_provider
        from cairn.core.reranker.interface import RerankerInterface

        class MyReranker(RerankerInterface):
            ...

        register_reranker_provider("my-backend", lambda cfg: MyReranker(cfg))
    """
    _providers[name] = factory
    logger.info("Registered reranker provider: %s", name)


def get_reranker(config: RerankerConfig) -> RerankerInterface:
    """Return the configured reranker backend.

    Checks the plugin registry first, then falls back to built-in providers.
    """
    # Check plugin registry
    if config.backend in _providers:
        return _providers[config.backend](config)

    # Built-in providers (lazy imports to avoid heavy deps at module load)
    if config.backend == "local":
        from cairn.core.reranker.local import LocalReranker
        return LocalReranker(config)
    elif config.backend == "bedrock":
        from cairn.core.reranker.bedrock import BedrockReranker
        return BedrockReranker(config)
    else:
        available = sorted(set(BUILT_IN_PROVIDERS + list(_providers.keys())))
        raise ValueError(
            f"Unknown reranker backend: {config.backend!r}. "
            f"Available: {', '.join(available)}"
        )


# For error messages and discovery
BUILT_IN_PROVIDERS = ["local", "bedrock"]
