"""Google Gemini LLM implementation via REST API."""

import json
import logging
import time
import urllib.request
import urllib.error

from cairn.config import LLMConfig
from cairn.core import stats
from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Known context sizes
CONTEXT_SIZES = {
    "gemini-2.0-flash": 1048576,
    "gemini-2.0-flash-lite": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-pro": 2097152,
}


class GeminiLLM(LLMInterface):
    """LLM via Google Gemini REST API (generativelanguage.googleapis.com).

    Uses the free-tier-compatible REST endpoint. No SDK dependency.
    """

    def __init__(self, config: LLMConfig):
        self.model = config.gemini_model
        self.api_key = config.gemini_api_key
        if not self.api_key:
            raise ValueError("CAIRN_GEMINI_API_KEY is required for gemini backend")
        logger.info("Gemini LLM ready: %s", self.model)

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate via Gemini generateContent API with retry on transient failures."""
        # Separate system instruction from conversation
        system_parts = []
        contents = []

        for msg in messages:
            if msg["role"] == "system":
                system_parts.append({"text": msg["content"]})
            else:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}],
                })

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.3,
            },
        }
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}

        payload = json.dumps(body).encode()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model}:generateContent?key={self.api_key}"
        )
        req = urllib.request.Request(
            url,
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
                    raise ValueError(f"Gemini returned invalid JSON: {raw[:200]}") from e

                # Parse response — candidates[0].content.parts[0].text
                candidates = result.get("candidates", [])
                if not candidates:
                    raise ValueError(f"Gemini returned no candidates: {list(result.keys())}")
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts or "text" not in parts[0]:
                    raise ValueError(f"Unexpected Gemini response structure: {candidates[0].keys()}")
                result_text = parts[0]["text"]
                if stats.llm_stats:
                    input_est = sum(len(m.get("content", "")) for m in messages) // 4
                    stats.llm_stats.record_call(tokens_est=input_est + len(result_text) // 4)
                return result_text

            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "Gemini transient error (attempt %d/3): HTTP %d. Retrying in %ds...",
                        attempt + 1, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "Gemini transient error (attempt %d/3): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
                continue

        if stats.llm_stats:
            stats.llm_stats.record_error(str(last_error))
        raise last_error  # All retries exhausted

    def get_model_name(self) -> str:
        return self.model

    def get_context_size(self) -> int:
        return CONTEXT_SIZES.get(self.model, 1048576)
