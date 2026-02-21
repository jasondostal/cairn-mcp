"""Local SentenceTransformer embedding engine. The default provider."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from cairn.config import EmbeddingConfig
from cairn.core import stats
from cairn.embedding.interface import EmbeddingInterface

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingEngine(EmbeddingInterface):
    """Wraps SentenceTransformer for text → vector conversion.

    Runs on CPU, loads lazily on first embed call.
    """

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self.config.model)
            self._model = SentenceTransformer(self.config.model)
            logger.info(
                "Embedding model loaded. Dimensions: %d",
                self._model.get_sentence_embedding_dimension(),
            )
        return self._model

    @property
    def dimensions(self) -> int:
        return self.config.dimensions

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a normalized float vector."""
        t0 = time.monotonic()
        vector = self.model.encode(text, normalize_embeddings=True)
        latency_ms = (time.monotonic() - t0) * 1000
        tokens_est = len(text) // 4
        if stats.embedding_stats:
            stats.embedding_stats.record_call(tokens_est=tokens_est)
        stats.emit_usage_event("embed", self.config.model, tokens_in=tokens_est, latency_ms=latency_ms)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns a list of normalized float vectors."""
        t0 = time.monotonic()
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        latency_ms = (time.monotonic() - t0) * 1000
        tokens_est = sum(len(t) // 4 for t in texts)
        if stats.embedding_stats:
            stats.embedding_stats.record_call(tokens_est=tokens_est)
        stats.emit_usage_event("embed.batch", self.config.model, tokens_in=tokens_est, latency_ms=latency_ms)
        return vectors.tolist()
