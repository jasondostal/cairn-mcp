"""Reranker interface ABC. Implementations must provide rerank()."""

from abc import ABC, abstractmethod


class RerankerInterface(ABC):
    """Abstract base for reranker backends.

    All rerankers score (query, candidate) pairs and return top-N by relevance.
    Candidates are dicts with at least 'id' and 'content' keys.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        """Rerank candidates by relevance to query.

        Args:
            query: The search query.
            candidates: List of dicts, each must have 'id' and 'content' keys.
            limit: Number of top results to return.

        Returns:
            Top-N candidates sorted by relevance, with 'rerank_score' attached.
        """
