"""AWS Bedrock Titan Text Embeddings V2 provider."""

import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

from cairn.config import EmbeddingConfig
from cairn.core import stats
from cairn.embedding.interface import EmbeddingInterface

logger = logging.getLogger(__name__)


class BedrockEmbedding(EmbeddingInterface):
    """Embedding via AWS Bedrock Titan Text Embeddings V2.

    Single-text-per-call API — embed_batch loops over texts.
    8,192 token context, configurable output dimensions (256/512/1024).
    """

    def __init__(self, config: EmbeddingConfig):
        self._dimensions = config.dimensions
        self._model_id = config.bedrock_model
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=config.bedrock_region,
        )
        logger.info(
            "Bedrock embedding ready: %s (region=%s, dimensions=%d)",
            self._model_id,
            config.bedrock_region,
            self._dimensions,
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        """Embed a single text string via Titan V2. Returns a normalized float vector."""
        body = json.dumps({
            "inputText": text,
            "dimensions": self._dimensions,
            "normalize": True,
        })

        t0 = time.monotonic()
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.invoke_model(
                    modelId=self._model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
                result = json.loads(response["body"].read())
                latency_ms = (time.monotonic() - t0) * 1000
                tokens_est = len(text) // 4
                if stats.embedding_stats:
                    stats.embedding_stats.record_call(tokens_est=tokens_est)
                stats.emit_usage_event("embed", self._model_id, tokens_in=tokens_est, latency_ms=latency_ms)
                return result["embedding"]
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in (
                    "ThrottlingException",
                    "ServiceUnavailableException",
                    "ModelTimeoutException",
                ):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "Bedrock embedding transient error (attempt %d/3): %s. Retrying in %ds...",
                        attempt + 1, error_code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

        latency_ms = (time.monotonic() - t0) * 1000
        if stats.embedding_stats:
            stats.embedding_stats.record_error(str(last_error))
        stats.emit_usage_event(
            "embed", self._model_id, latency_ms=latency_ms,
            success=False, error_message=str(last_error),
        )
        raise last_error  # All retries exhausted

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Titan V2 is single-text per call, so we loop."""
        return [self.embed(text) for text in texts]
