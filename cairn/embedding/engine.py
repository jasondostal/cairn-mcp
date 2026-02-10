"""Local SentenceTransformer embedding engine. The default provider."""

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from cairn.config import EmbeddingConfig
from cairn.embedding.interface import EmbeddingInterface

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
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns a list of normalized float vectors."""
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        return vectors.tolist()
