"""AWS Bedrock LLM implementation via Converse API."""

import logging
import time

import boto3
from botocore.exceptions import ClientError

from cairn.config import LLMConfig
from cairn.core import stats
from cairn.llm.interface import LLMInterface, LLMResponse, ToolCallInfo

logger = logging.getLogger(__name__)

# Model context sizes (known models)
CONTEXT_SIZES = {
    "us.meta.llama3-2-90b-instruct-v1:0": 128000,
    "us.meta.llama3-2-11b-instruct-v1:0": 128000,
    "anthropic.claude-3-5-sonnet-20241022-v2:0": 200000,
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": 200000,
    "openai.gpt-oss-120b-1:0": 128000,
    "moonshotai.kimi-k2.5": 128000,
}

# Reasoning models return reasoning tokens before the answer text.
# We need to bump max_tokens so reasoning doesn't consume the entire budget.
REASONING_MODELS = {"openai.gpt-oss-120b-1:0"}


class BedrockLLM(LLMInterface):
    """LLM via AWS Bedrock Converse API."""

    def __init__(self, config: LLMConfig):
        self.model_id = config.bedrock_model
        self.region = config.bedrock_region
        self._client = boto3.client("bedrock-runtime", region_name=self.region)
        self._tools_unsupported = False
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

        # Reasoning models consume tokens on chain-of-thought before answering
        effective_max = max_tokens * 4 if self.model_id in REASONING_MODELS else max_tokens

        kwargs = {
            "modelId": self.model_id,
            "messages": converse_messages,
            "inferenceConfig": {"maxTokens": effective_max, "temperature": 0.3},
        }
        if system_prompts:
            kwargs["system"] = system_prompts

        t0 = time.monotonic()
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.converse(**kwargs)
                # Defensive parsing — handle both standard and reasoning models
                output = response.get("output", {})
                message = output.get("message", {})
                content = message.get("content", [])
                # Find the text block (reasoning models put reasoning first, answer second)
                result_text = None
                for block in content:
                    if "text" in block:
                        result_text = block["text"]
                        break
                if result_text is None:
                    raise ValueError(f"No text block in Bedrock response: {[list(b.keys()) for b in content]}")
                latency_ms = (time.monotonic() - t0) * 1000
                usage = response.get("usage", {})
                tokens_in = usage.get("inputTokens") or sum(len(m.get("content", "")) for m in messages) // 4
                tokens_out = usage.get("outputTokens") or len(result_text) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
                stats.emit_usage_event(
                    "llm.generate", self.model_id,
                    tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
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

    # -- Tool calling support --

    def supports_tool_use(self) -> bool:
        return not self._tools_unsupported

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate with tool calling via Bedrock Converse API."""
        if self._tools_unsupported:
            text = self.generate(messages, max_tokens)
            return LLMResponse(text=text, stop_reason="end_turn")

        system_prompts, converse_messages = self._prepare_tool_messages(messages)

        bedrock_tools = [
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"json": t["parameters"]},
                }
            }
            for t in tools
        ]

        effective_max = max_tokens * 4 if self.model_id in REASONING_MODELS else max_tokens

        kwargs = {
            "modelId": self.model_id,
            "messages": converse_messages,
            "inferenceConfig": {"maxTokens": effective_max, "temperature": 0.3},
            "toolConfig": {"tools": bedrock_tools},
        }
        if system_prompts:
            kwargs["system"] = system_prompts

        t0 = time.monotonic()
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.converse(**kwargs)

                output = response.get("output", {})
                message = output.get("message", {})
                content = message.get("content", [])
                stop_reason = response.get("stopReason", "end_turn")

                text = None
                tool_calls = []
                for block in content:
                    if "text" in block:
                        text = block["text"]
                    elif "toolUse" in block:
                        tu = block["toolUse"]
                        tool_calls.append(ToolCallInfo(
                            id=tu["toolUseId"],
                            name=tu["name"],
                            input=tu["input"],
                        ))

                latency_ms = (time.monotonic() - t0) * 1000
                usage = response.get("usage", {})
                tokens_in = usage.get("inputTokens") or sum(
                    len(m.get("content", "")) for m in messages
                    if isinstance(m.get("content"), str)
                ) // 4
                tokens_out = usage.get("outputTokens") or (len(text or "") + sum(len(str(tc.input)) for tc in tool_calls)) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
                stats.emit_usage_event(
                    "llm.generate_with_tools", self.model_id,
                    tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
                )

                return LLMResponse(
                    text=text,
                    tool_calls=tool_calls,
                    stop_reason="tool_use" if stop_reason == "tool_use" else "end_turn",
                )

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "ValidationException" and "toolConfig" in str(e):
                    logger.warning(
                        "Model %s does not support tool use, disabling for this session",
                        self.model_id,
                    )
                    self._tools_unsupported = True
                    text = self.generate(messages, max_tokens)
                    return LLMResponse(text=text, stop_reason="end_turn")
                if error_code in ("ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"):
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning("Bedrock transient error (attempt %d/3): %s", attempt + 1, error_code)
                    time.sleep(wait)
                    continue
                raise

        latency_ms = (time.monotonic() - t0) * 1000
        if stats.llm_stats:
            stats.llm_stats.record_error(str(last_error))
        stats.emit_usage_event(
            "llm.generate_with_tools", self.model_id, latency_ms=latency_ms,
            success=False, error_message=str(last_error),
        )
        raise last_error

    def _prepare_tool_messages(self, messages: list[dict]) -> tuple[list, list]:
        """Convert intermediate message format to Bedrock Converse format.

        Handles plain messages, assistant messages with tool_calls,
        and tool_result messages from the agent loop.
        """
        system_prompts = []
        converse_messages = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                system_prompts.append({"text": msg["content"]})

            elif role == "user":
                converse_messages.append({
                    "role": "user",
                    "content": [{"text": msg["content"]}],
                })

            elif role == "assistant":
                content = []
                if msg.get("content"):
                    content.append({"text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    content.append({
                        "toolUse": {
                            "toolUseId": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        }
                    })
                if content:
                    converse_messages.append({"role": "assistant", "content": content})

            elif role == "tool_result":
                content = []
                for tr in msg.get("results", []):
                    result_content = [{"text": tr["content"]}] if tr.get("content") else [{"text": "OK"}]
                    content.append({
                        "toolResult": {
                            "toolUseId": tr["tool_use_id"],
                            "content": result_content,
                            "status": tr.get("status", "success"),
                        }
                    })
                if content:
                    converse_messages.append({"role": "user", "content": content})

        return system_prompts, converse_messages

    def get_model_name(self) -> str:
        return self.model_id

    def get_context_size(self) -> int:
        return CONTEXT_SIZES.get(self.model_id, 128000)
