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
import urllib.error
import urllib.request
from collections.abc import Iterator

from cairn.config import LLMConfig
from cairn.core import stats
from cairn.llm.interface import LLMInterface, LLMResponse, StreamEvent, ToolCallInfo

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(LLMInterface):
    """LLM via any OpenAI-compatible /v1/chat/completions endpoint.

    No SDK dependency — uses urllib like the other providers.
    """

    def __init__(self, config: LLMConfig):
        self.model = config.openai_model
        self.api_key = config.openai_api_key
        self.base_url = config.openai_base_url.rstrip("/")
        # Normalize: strip /v1 suffix if present — we append it ourselves
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        if not self.api_key:
            raise ValueError("CAIRN_OPENAI_API_KEY is required for openai backend")
        self._tools_unsupported = False
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
                "User-Agent": "cairn/0.55.0",
            },
        )

        max_retries = 5
        t0 = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"API returned invalid JSON: {raw[:200]}") from e

                # Parse response — choices[0].message.content
                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(f"API returned no choices: {list(result.keys())}")
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning_content")
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
                    wait = min(2 ** attempt + 1, 30)  # 2s, 3s, 5s, 9s, 17s
                    logger.warning(
                        "API transient error (attempt %d/%d): HTTP %d. Retrying in %ds...",
                        attempt + 1, max_retries, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = min(2 ** attempt + 1, 30)
                logger.warning(
                    "API transient error (attempt %d/%d): %s. Retrying in %ds...",
                    attempt + 1, max_retries, e, wait,
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
        assert last_error is not None
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
                "User-Agent": "cairn/0.55.0",
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

    # -- Tool calling support --

    def supports_tool_use(self) -> bool:
        return not self._tools_unsupported

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate with tool calling via OpenAI-compatible API."""
        if self._tools_unsupported:
            text = self.generate(messages, max_tokens)
            return LLMResponse(text=text, stop_reason="end_turn")

        openai_messages = self._prepare_tool_messages(messages)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

        payload = json.dumps({
            "model": self.model,
            "messages": openai_messages,
            "tools": openai_tools,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "cairn/0.59.2",
            },
        )

        t0 = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"API returned invalid JSON: {raw[:200]}") from e

                choices = result.get("choices", [])
                if not choices:
                    raise ValueError(f"API returned no choices: {list(result.keys())}")

                msg = choices[0].get("message", {})
                finish_reason = choices[0].get("finish_reason", "stop")
                text = msg.get("content")
                raw_tool_calls = msg.get("tool_calls") or []

                tool_calls = []
                for tc in raw_tool_calls:
                    func = tc.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCallInfo(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        input=args,
                    ))

                latency_ms = (time.monotonic() - t0) * 1000
                usage = result.get("usage", {})
                tokens_in = usage.get("prompt_tokens") or sum(
                    len(m.get("content", "")) for m in messages
                    if isinstance(m.get("content"), str)
                ) // 4
                tokens_out = usage.get("completion_tokens") or (len(text or "") + sum(len(str(tc.input)) for tc in tool_calls)) // 4
                if stats.llm_stats:
                    stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
                stats.emit_usage_event(
                    "llm.generate_with_tools", self.model,
                    tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
                )

                # Detect tool use: finish_reason "tool_calls" or presence of tool_calls
                is_tool_use = finish_reason == "tool_calls" or (tool_calls and finish_reason != "stop")
                return LLMResponse(
                    text=text,
                    tool_calls=tool_calls,
                    stop_reason="tool_use" if is_tool_use else "end_turn",
                )

            except urllib.error.HTTPError as e:
                # Graceful degradation: if 400/422 mentions tools, model doesn't support them
                if e.code in (400, 422):
                    try:
                        err_body = e.read().decode("utf-8", errors="replace")
                    except Exception:
                        err_body = ""
                    if "tool" in err_body.lower() or "function" in err_body.lower():
                        logger.warning(
                            "Model %s does not support tool use, disabling for this session",
                            self.model,
                        )
                        self._tools_unsupported = True
                        text = self.generate(messages, max_tokens)
                        return LLMResponse(text=text, stop_reason="end_turn")
                if e.code in (429, 500, 502, 503):
                    last_error = e
                    wait = min(2 ** attempt + 1, 30)
                    logger.warning(
                        "API transient error (attempt %d/5): HTTP %d. Retrying in %ds...",
                        attempt + 1, e.code, wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                wait = min(2 ** attempt + 1, 30)
                logger.warning(
                    "API transient error (attempt %d/5): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
                continue

        latency_ms = (time.monotonic() - t0) * 1000
        if stats.llm_stats:
            stats.llm_stats.record_error(str(last_error))
        stats.emit_usage_event(
            "llm.generate_with_tools", self.model, latency_ms=latency_ms,
            success=False, error_message=str(last_error),
        )
        assert last_error is not None
        raise last_error

    def generate_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> Iterator[StreamEvent]:
        """Stream generation with tool support via OpenAI-compatible API."""
        if self._tools_unsupported:
            yield from self.generate_stream(messages, max_tokens)
            return

        openai_messages = self._prepare_tool_messages(messages)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

        payload = json.dumps({
            "model": self.model,
            "messages": openai_messages,
            "tools": openai_tools,
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
                "User-Agent": "cairn/0.59.2",
            },
        )

        t0 = time.monotonic()
        full_text = ""
        # Accumulate tool calls by index across streamed deltas
        active_tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}
        finish_reason = "stop"

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # Track finish_reason
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]

                    # Text content
                    token = delta.get("content", "")
                    if token:
                        full_text += token
                        yield StreamEvent(type="text_delta", text=token)

                    # Tool call deltas
                    for tc_delta in delta.get("tool_calls", []):
                        idx = tc_delta.get("index", 0)
                        if idx not in active_tool_calls:
                            active_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        tc = active_tool_calls[idx]
                        if tc_delta.get("id"):
                            tc["id"] = tc_delta["id"]
                        func = tc_delta.get("function", {})
                        if func.get("name"):
                            tc["name"] = func["name"]
                        if func.get("arguments"):
                            tc["arguments"] += func["arguments"]

            # Build final tool_calls list
            tool_calls = []
            for idx in sorted(active_tool_calls):
                tc = active_tool_calls[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCallInfo(
                    id=tc["id"], name=tc["name"], input=args,
                ))

            latency_ms = (time.monotonic() - t0) * 1000
            tokens_out = len(full_text) // 4
            tokens_in = sum(
                len(m.get("content", "")) for m in messages
                if isinstance(m.get("content"), str)
            ) // 4
            if stats.llm_stats:
                stats.llm_stats.record_call(tokens_est=tokens_in + tokens_out)
            stats.emit_usage_event(
                "llm.generate_with_tools", self.model,
                tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
            )

        except urllib.error.HTTPError as e:
            if e.code in (400, 422):
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = ""
                if "tool" in err_body.lower() or "function" in err_body.lower():
                    logger.warning(
                        "Model %s does not support tool use, disabling for this session",
                        self.model,
                    )
                    self._tools_unsupported = True
                    yield from self.generate_stream(messages, max_tokens)
                    return
            logger.error("OpenAI-compat streaming error: %s", e)
            if stats.llm_stats:
                stats.llm_stats.record_error(str(e))
            raise
        except Exception as e:
            logger.error("OpenAI-compat streaming error: %s", e)
            if stats.llm_stats:
                stats.llm_stats.record_error(str(e))
            raise

        is_tool_use = finish_reason == "tool_calls" or (tool_calls and finish_reason != "stop")
        yield StreamEvent(
            type="response_complete",
            response=LLMResponse(
                text=full_text or None,
                tool_calls=tool_calls,
                stop_reason="tool_use" if is_tool_use else "end_turn",
            ),
        )

    def _prepare_tool_messages(self, messages: list[dict]) -> list[dict]:
        """Convert intermediate message format to OpenAI chat format.

        Handles plain messages, assistant messages with tool_calls,
        and tool_result messages from the agent loop.
        """
        openai_messages = []

        for msg in messages:
            role = msg.get("role")

            if role in ("system", "user"):
                openai_messages.append({
                    "role": role,
                    "content": msg["content"],
                })

            elif role == "assistant":
                out: dict = {"role": "assistant"}
                if msg.get("content"):
                    out["content"] = msg["content"]
                if msg.get("tool_calls"):
                    out["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["input"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                openai_messages.append(out)

            elif role == "tool_result":
                # Each tool result becomes a separate message with role "tool"
                for tr in msg.get("results", []):
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_use_id"],
                        "content": tr.get("content") or "OK",
                    })

        return openai_messages

    def get_model_name(self) -> str:
        return self.model

    def get_context_size(self) -> int:
        # Can't reliably detect this from the API, use a safe default
        return 128000
