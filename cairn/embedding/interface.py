"""Embedding engine ABC. Implementations must provide embed() and embed_batch()."""

from abc import ABC, abstractmethod


class EmbeddingInterface(ABC):
    """Abstract base for embedding backends.

    All embedding engines must expose dimensions and provide embed/embed_batch.
    The vector dimensions must match the database pgvector column size.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding vector dimensionality."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a normalized float vector."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns a list of normalized float vectors."""
