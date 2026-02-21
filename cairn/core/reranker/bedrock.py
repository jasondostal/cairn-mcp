"""AWS Bedrock Rerank API provider."""

from __future__ import annotations

import logging

from cairn.config import RerankerConfig
from cairn.core.reranker.interface import RerankerInterface

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cohere.rerank-v3-5:0"
# Bedrock rerank API caps at 1000 documents per request
MAX_DOCS = 500
# Truncate long documents to avoid token limits
MAX_DOC_CHARS = 4000


class BedrockReranker(RerankerInterface):
    """Reranker using AWS Bedrock Rerank API.

    Lazy-initializes the boto3 client on first rerank() call.
    """

    def __init__(self, config: RerankerConfig):
        self._model_id = config.bedrock_model
        self._region = config.bedrock_region
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
        if not candidates or len(candidates) <= limit:
            return candidates

        client = self._get_client()

        sources = []
        for c in candidates[:MAX_DOCS]:
            text = c["content"][:MAX_DOC_CHARS] if c["content"] else ""
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

        reranked = []
        for result in response["results"]:
            idx = result["index"]
            if idx < len(candidates):
                candidates[idx]["rerank_score"] = float(result["relevanceScore"])
                reranked.append(candidates[idx])

        return reranked[:limit]
