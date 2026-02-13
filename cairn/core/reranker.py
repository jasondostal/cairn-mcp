"""Reranking for search result refinement.

After RRF fusion produces a broad candidate set (top-50), a reranker
scores each (query, content) pair for fine-grained relevance. This narrows
the candidate pool to the most relevant results.

Two backends:
  - local: cross-encoder/ms-marco-MiniLM-L-6-v2 — 22M params, CPU inference
  - bedrock: Cohere Rerank 3.5 via AWS Bedrock Rerank API — GPU-backed, fast
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Default cross-encoder model — small, fast, good at passage relevance
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Bedrock reranker defaults
DEFAULT_BEDROCK_RERANK_MODEL = "amazon.rerank-v1:0"
# Bedrock rerank API caps at 1000 documents per request
BEDROCK_MAX_DOCS = 500
# Truncate long documents to avoid token limits
BEDROCK_MAX_DOC_CHARS = 4000


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


class BedrockReranker:
    """Reranker using AWS Bedrock Rerank API (Cohere Rerank 3.5)."""

    def __init__(
        self,
        model_id: str = DEFAULT_BEDROCK_RERANK_MODEL,
        region: str = "us-east-1",
    ):
        self._model_id = model_id
        self._region = region
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self._region,
            )
            logger.info("Bedrock reranker initialized: %s (%s)", self._model_id, self._region)
        return self._client

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        """Rerank candidates via Bedrock Rerank API.

        Same interface as Reranker.rerank() — drop-in replacement.
        """
        if not candidates or len(candidates) <= limit:
            return candidates

        client = self._get_client()

        # Build sources list — truncate long docs
        sources = []
        for c in candidates[:BEDROCK_MAX_DOCS]:
            text = c["content"][:BEDROCK_MAX_DOC_CHARS] if c["content"] else ""
            sources.append({
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {"text": text},
                },
            })

        try:
            response = client.rerank(
                queries=[{
                    "type": "TEXT",
                    "textQuery": {"text": query},
                }],
                sources=sources,
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {
                            "modelArn": f"arn:aws:bedrock:{self._region}::foundation-model/{self._model_id}",
                        },
                        "numberOfResults": limit,
                    },
                },
            )
        except Exception:
            logger.warning("Bedrock reranking failed, returning candidates as-is", exc_info=True)
            return candidates[:limit]

        # Map results back — Bedrock returns them sorted by relevance
        reranked = []
        for result in response["results"]:
            idx = result["index"]
            if idx < len(candidates):
                candidates[idx]["rerank_score"] = float(result["relevanceScore"])
                reranked.append(candidates[idx])

        return reranked[:limit]


def get_reranker(
    backend: str = "local",
    model: str | None = None,
    region: str = "us-east-1",
) -> Reranker | BedrockReranker:
    """Factory for reranker instances."""
    if backend == "bedrock":
        return BedrockReranker(
            model_id=model or DEFAULT_BEDROCK_RERANK_MODEL,
            region=region,
        )
    else:
        return Reranker(model_name=model or DEFAULT_RERANKER_MODEL)
