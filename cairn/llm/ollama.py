"""Ollama LLM implementation for local fallback."""

import json
import logging
import time
import urllib.request
import urllib.error

from cairn.config import LLMConfig
from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class OllamaLLM(LLMInterface):
    """LLM via local Ollama API."""

    def __init__(self, config: LLMConfig):
        self.model = config.ollama_model
        self.base_url = config.ollama_url.rstrip("/")
        logger.info("Ollama LLM ready: %s at %s", self.model, self.base_url)

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate via Ollama chat API with retry on transient failures."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Ollama returned invalid JSON: {raw[:200]}") from e
                # Defensive parsing
                message = result.get("message", {})
                content = message.get("content")
                if content is None:
                    raise ValueError(f"Unexpected Ollama response structure: {list(result.keys())}")
                return content
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning("Ollama transient error (attempt %d/3): %s. Retrying in %ds...", attempt + 1, e, wait)
                time.sleep(wait)
                continue

        raise last_error  # All retries exhausted

    def get_model_name(self) -> str:
        return self.model

    def get_context_size(self) -> int:
        return 8192  # Conservative default for 7B models
