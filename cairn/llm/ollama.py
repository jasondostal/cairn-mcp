"""Ollama LLM implementation for local fallback."""

import json
import logging
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
        """Generate via Ollama chat API."""
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

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["message"]["content"]

    def get_model_name(self) -> str:
        return self.model

    def get_context_size(self) -> int:
        return 8192  # Conservative default for 7B models
