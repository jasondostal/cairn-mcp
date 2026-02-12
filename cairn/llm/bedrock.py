"""AWS Bedrock LLM implementation via Converse API."""

import logging
import time

import boto3
from botocore.exceptions import ClientError

from cairn.config import LLMConfig
from cairn.core import stats
from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Model context sizes (known models)
CONTEXT_SIZES = {
    "us.meta.llama3-2-90b-instruct-v1:0": 128000,
    "us.meta.llama3-2-11b-instruct-v1:0": 128000,
    "anthropic.claude-3-5-sonnet-20241022-v2:0": 200000,
}


class BedrockLLM(LLMInterface):
    """LLM via AWS Bedrock Converse API."""

    def __init__(self, config: LLMConfig):
        self.model_id = config.bedrock_model
        self.region = config.bedrock_region
        self._client = boto3.client("bedrock-runtime", region_name=self.region)
        logger.info(
            "Bedrock LLM ready: %s (region=%s, ctx=%d)",
            self.model_id,
            self.region,
            self.get_context_size(),
        )

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate via Bedrock Converse API with retry on transient failures."""
        # Separate system prompt from conversation messages
        system_prompts = []
        converse_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompts.append({"text": msg["content"]})
            else:
                converse_messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}],
                })

        kwargs = {
            "modelId": self.model_id,
            "messages": converse_messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.3},
        }
        if system_prompts:
            kwargs["system"] = system_prompts

        t0 = time.monotonic()
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.converse(**kwargs)
                # Defensive parsing — don't trust nested structure
                output = response.get("output", {})
                message = output.get("message", {})
                content = message.get("content", [])
                if not content or "text" not in content[0]:
                    raise ValueError(f"Unexpected Bedrock response structure: {list(response.keys())}")
                result_text = content[0]["text"]
                latency_ms = (time.monotonic() - t0) * 1000
                input_est = sum(len(m.get("content", "")) for m in messages) // 4
                output_est = len(result_text) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=input_est + output_est)
                stats.emit_usage_event(
                    "llm.generate", self.model_id,
                    tokens_in=input_est, tokens_out=output_est, latency_ms=latency_ms,
                )
                return result_text
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning("Bedrock transient error (attempt %d/3): %s. Retrying in %ds...", attempt + 1, error_code, wait)
                    time.sleep(wait)
                    continue
                raise
            except (KeyError, IndexError, TypeError) as e:
                raise ValueError(f"Failed to parse Bedrock response: {e}") from e

        latency_ms = (time.monotonic() - t0) * 1000
        if stats.llm_stats:
            stats.llm_stats.record_error(str(last_error))
        stats.emit_usage_event(
            "llm.generate", self.model_id, latency_ms=latency_ms,
            success=False, error_message=str(last_error),
        )
        raise last_error  # All retries exhausted

    def get_model_name(self) -> str:
        return self.model_id

    def get_context_size(self) -> int:
        return CONTEXT_SIZES.get(self.model_id, 128000)
