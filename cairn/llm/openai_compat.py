"""OpenAI-compatible LLM implementation.

Works with any API that speaks the /v1/chat/completions format:
  - OpenAI (api.openai.com)
  - Groq (api.groq.com)
  - Together AI (api.together.xyz)
  - Mistral (api.mistral.ai)
  - LM Studio (localhost)
  - vLLM (localhost)
  - Any OpenAI-compatible endpoint
"""

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


class OpenAICompatibleLLM(LLMInterface):
    """LLM via any OpenAI-compatible /v1/chat/completions endpoint.

    No SDK dependency — uses urllib like the other providers.
    """

    def __init__(self, config: LLMConfig):
        self.model = config.openai_model
        self.api_key = config.openai_api_key
        self.base_url = config.openai_base_url.rstrip("/")
        if not self.api_key:
            raise ValueError("CAIRN_OPENAI_API_KEY is required for openai backend")
        logger.info("OpenAI-compatible LLM ready: %s at %s", self.model, self.base_url)

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate via OpenAI chat completions API with retry on transient failures."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
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
                    raise ValueError(f"API returned invalid JSON: {raw[:200]}") from e

                # Parse response — choices[0].message.content
                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(f"API returned no choices: {list(result.keys())}")
                content = choices[0].get("message", {}).get("content")
                if content is None:
                    raise ValueError(f"Unexpected response structure: {choices[0].keys()}")
                latency_ms = (time.monotonic() - t0) * 1000
                usage = result.get("usage", {})
                tokens_in = usage.get("prompt_tokens") or sum(len(m.get("content", "")) for m in messages) // 4
                tokens_out = usage.get("completion_tokens") or len(content) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
                stats.emit_usage_event(
                    "llm.generate", self.model,
                    tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
                )
                return content

            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "API transient error (attempt %d/3): HTTP %d. Retrying in %ds...",
                        attempt + 1, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "API transient error (attempt %d/3): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
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
        """Stream text via OpenAI-compatible /v1/chat/completions with stream=true."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": True,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        t0 = time.monotonic()
        full_text = ""
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]  # strip "data: " prefix
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_text += token
                        yield StreamEvent(type="text_delta", text=token)

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
            logger.error("OpenAI-compat streaming error: %s", e)
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
        # Can't reliably detect this from the API, use a safe default
        return 128000
