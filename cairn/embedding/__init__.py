"""Embedding backend factory with pluggable provider registry.

Built-in providers: local (SentenceTransformer), bedrock (Titan Text Embeddings V2),
openai (any /v1/embeddings API).
Register custom providers via ``register_embedding_provider(name, factory_fn)``.
"""

from __future__ import annotations

import logging
from typing import Callable

from cairn.config import EmbeddingConfig
from cairn.embedding.interface import EmbeddingInterface

logger = logging.getLogger(__name__)

# Provider registry: name -> factory function(config) -> EmbeddingInterface
_providers: dict[str, Callable[[EmbeddingConfig], EmbeddingInterface]] = {}


def register_embedding_provider(
    name: str,
    factory: Callable[[EmbeddingConfig], EmbeddingInterface],
) -> None:
    """Register a custom embedding provider.

    Args:
        name: Backend name (matches CAIRN_EMBEDDING_BACKEND env var).
        factory: Callable that takes EmbeddingConfig and returns an EmbeddingInterface.

    Example::

        from cairn.embedding import register_embedding_provider
        from cairn.embedding.interface import EmbeddingInterface

        class OpenAIEmbedding(EmbeddingInterface):
            ...

        register_embedding_provider("openai", lambda cfg: OpenAIEmbedding(cfg))
    """
    _providers[name] = factory
    logger.info("Registered embedding provider: %s", name)


def get_embedding_engine(config: EmbeddingConfig) -> EmbeddingInterface:
    """Return the configured embedding backend.

    Checks the plugin registry first, then falls back to built-in local engine.
    """
    backend = getattr(config, "backend", "local")

    # Check plugin registry
    if backend in _providers:
        return _providers[backend](config)

    # Built-in backends
    if backend == "local":
        from cairn.embedding.engine import EmbeddingEngine
        return EmbeddingEngine(config)
    elif backend == "bedrock":
        from cairn.embedding.bedrock import BedrockEmbedding
        return BedrockEmbedding(config)
    elif backend == "openai":
        from cairn.embedding.openai_compat import OpenAICompatibleEmbedding
        return OpenAICompatibleEmbedding(config)
    else:
        available = sorted(set(["local", "bedrock", "openai"] + list(_providers.keys())))
        raise ValueError(
            f"Unknown embedding backend: {backend!r}. "
            f"Available: {', '.join(available)}"
        )
