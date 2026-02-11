"""OpenAI-compatible embedding implementation.

Works with any API that speaks the /v1/embeddings format:
  - OpenAI (api.openai.com)
  - Ollama (localhost:11434)
  - vLLM (localhost)
  - LM Studio (localhost)
  - Together AI (api.together.xyz)
  - Any OpenAI-compatible endpoint

No SDK dependency — uses urllib like the LLM provider.
"""

import json
import logging
import time
import urllib.request
import urllib.error

from cairn.config import EmbeddingConfig
from cairn.core import stats
from cairn.embedding.interface import EmbeddingInterface

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbedding(EmbeddingInterface):
    """Embedding via any OpenAI-compatible /v1/embeddings endpoint.

    No SDK dependency — uses urllib like the other providers.
    Empty API key = no Authorization header (for local endpoints like Ollama).
    """

    def __init__(self, config: EmbeddingConfig):
        self._dimensions = config.dimensions
        self._model = config.openai_model
        self._api_key = config.openai_api_key
        self._base_url = config.openai_base_url.rstrip("/")
        logger.info(
            "OpenAI-compatible embedding ready: %s at %s (dimensions=%d, auth=%s)",
            self._model,
            self._base_url,
            self._dimensions,
            "yes" if self._api_key else "no",
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _build_request(self, payload: bytes) -> urllib.request.Request:
        """Build HTTP request with optional auth header."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return urllib.request.Request(
            f"{self._base_url}/v1/embeddings",
            data=payload,
            headers=headers,
        )

    def embed(self, text: str) -> list[float]:
        """Embed a single text string with retry on transient failures."""
        payload = json.dumps({
            "model": self._model,
            "input": text,
        }).encode()

        req = self._build_request(payload)

        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"API returned invalid JSON: {raw[:200]}") from e

                data = result.get("data", [])
                if not data:
                    raise ValueError(f"API returned no data: {list(result.keys())}")
                embedding = data[0].get("embedding")
                if embedding is None:
                    raise ValueError(f"Unexpected response structure: {data[0].keys()}")
                if stats.embedding_stats:
                    stats.embedding_stats.record_call(tokens_est=len(text) // 4)
                return embedding

            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "Embedding API transient error (attempt %d/3): HTTP %d. Retrying in %ds...",
                        attempt + 1, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "Embedding API transient error (attempt %d/3): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
                continue

        if stats.embedding_stats:
            stats.embedding_stats.record_error(str(last_error))
        raise last_error  # All retries exhausted

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts using native batch support.

        The OpenAI /v1/embeddings API accepts a list of inputs and returns
        embeddings with an `index` field. We sort by index to guarantee order.
        """
        if not texts:
            return []

        payload = json.dumps({
            "model": self._model,
            "input": texts,
        }).encode()

        req = self._build_request(payload)

        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"API returned invalid JSON: {raw[:200]}") from e

                data = result.get("data", [])
                if len(data) != len(texts):
                    raise ValueError(
                        f"Expected {len(texts)} embeddings, got {len(data)}"
                    )

                # Sort by index to guarantee order matches input
                data.sort(key=lambda d: d.get("index", 0))
                embeddings = [d["embedding"] for d in data]

                if stats.embedding_stats:
                    total_tokens = sum(len(t) // 4 for t in texts)
                    stats.embedding_stats.record_call(tokens_est=total_tokens)
                return embeddings

            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "Embedding API batch transient error (attempt %d/3): HTTP %d. Retrying in %ds...",
                        attempt + 1, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "Embedding API batch transient error (attempt %d/3): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
                continue

        if stats.embedding_stats:
            stats.embedding_stats.record_error(str(last_error))
        raise last_error  # All retries exhausted
