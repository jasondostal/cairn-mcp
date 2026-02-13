"""Local cross-encoder reranker (sentence-transformers)."""

from __future__ import annotations

import logging

from cairn.config import RerankerConfig
from cairn.core.reranker.interface import RerankerInterface

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class LocalReranker(RerankerInterface):
    """Lazy-loaded cross-encoder for reranking search candidates.

    Uses sentence-transformers CrossEncoder. 22M params, CPU inference.
    Model is downloaded and loaded on first rerank() call.
    """

    def __init__(self, config: RerankerConfig):
        self._model_name = config.model
        self._model = None

    def _load_model(self):
        """Lazy-load the cross-encoder on first use."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            logger.info("Local reranker loaded: %s", self._model_name)
        except Exception:
            logger.warning("Failed to load reranker model: %s", self._model_name, exc_info=True)
            raise

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        if not candidates or len(candidates) <= limit:
            return candidates

        self._load_model()

        pairs = [(query, c["content"]) for c in candidates]

        try:
            scores = self._model.predict(pairs)
        except Exception:
            logger.warning("Reranking failed, returning candidates as-is", exc_info=True)
            return candidates[:limit]

        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)

        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates[:limit]
