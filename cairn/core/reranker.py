"""Cross-encoder reranking for search result refinement.

After RRF fusion produces a broad candidate set (top-50), a cross-encoder
scores each (query, content) pair for fine-grained relevance. This narrows
the candidate pool to the most relevant results.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 — 22M params, ~5ms/pair.
sentence-transformers is already a dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Default cross-encoder model — small, fast, good at passage relevance
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """Lazy-loaded cross-encoder for reranking search candidates."""

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy-load the cross-encoder on first use."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            logger.info("Reranker loaded: %s", self._model_name)
        except Exception:
            logger.warning("Failed to load reranker model: %s", self._model_name, exc_info=True)
            raise

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        """Rerank candidates by cross-encoder relevance score.

        Args:
            query: The search query.
            candidates: List of dicts, each must have 'id' and 'content' keys.
            limit: Number of top results to return.

        Returns:
            Top-N candidates sorted by cross-encoder score, with 'rerank_score' attached.
        """
        if not candidates or len(candidates) <= limit:
            return candidates

        self._load_model()

        # Build (query, content) pairs for scoring
        pairs = [(query, c["content"]) for c in candidates]

        try:
            scores = self._model.predict(pairs)
        except Exception:
            logger.warning("Reranking failed, returning candidates as-is", exc_info=True)
            return candidates[:limit]

        # Attach scores and sort
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)

        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates[:limit]
