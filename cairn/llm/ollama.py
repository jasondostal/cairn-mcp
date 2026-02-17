"""Ollama LLM implementation for local fallback."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from collections.abc import Iterator

from cairn.config import LLMConfig
from cairn.core import stats
from cairn.llm.interface import LLMInterface, LLMResponse, StreamEvent

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
            "think": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.monotonic()
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
                latency_ms = (time.monotonic() - t0) * 1000
                tokens_in = result.get("prompt_eval_count") or sum(len(m.get("content", "")) for m in messages) // 4
                tokens_out = result.get("eval_count") or len(content) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
                stats.emit_usage_event(
                    "llm.generate", self.model,
                    tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
                )
                return content
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning("Ollama transient error (attempt %d/3): %s. Retrying in %ds...", attempt + 1, e, wait)
                time.sleep(wait)
                continue

        latency_ms = (time.monotonic() - t0) * 1000
        if stats.llm_stats:
            stats.llm_stats.record_error(str(last_error))
        stats.emit_usage_event(
            "llm.generate", self.model, latency_ms=latency_ms,
            success=False, error_message=str(last_error),
        )
        raise last_error  # All retries exhausted

    def generate_stream(
        self, messages: list[dict], max_tokens: int = 1024,
    ) -> Iterator[StreamEvent]:
        """Stream text via Ollama chat API (NDJSON line-by-line)."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.monotonic()
        full_text = ""
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_text += token
                        yield StreamEvent(type="text_delta", text=token)
                    if chunk.get("done"):
                        break

            latency_ms = (time.monotonic() - t0) * 1000
            tokens_out = len(full_text) // 4
            tokens_in = sum(len(m.get("content", "")) for m in messages) // 4
            if stats.llm_stats:
                stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
            stats.emit_usage_event(
                "llm.generate", self.model,
                tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
            )
        except Exception as e:
            logger.error("Ollama streaming error: %s", e)
            if stats.llm_stats:
                stats.llm_stats.record_error(str(e))
            raise

        yield StreamEvent(
            type="response_complete",
            response=LLMResponse(text=full_text, stop_reason="end_turn"),
        )

    def get_model_name(self) -> str:
        return self.model

    def get_context_size(self) -> int:
        return 8192  # Conservative default for 7B models
