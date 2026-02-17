"""LLM interface ABC. Implementations must provide generate()."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class ToolCallInfo:
    """A single tool call requested by the LLM."""
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """Structured response from generate_with_tools()."""
    text: str | None = None
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" or "tool_use"


@dataclass
class StreamEvent:
    """A single event in a streaming LLM response.

    Event types:
      - text_delta: incremental text token (text field set)
      - response_complete: LLM finished generating (response field set)
    """
    type: str  # "text_delta" | "response_complete"
    text: str | None = None
    response: LLMResponse | None = None


class LLMInterface(ABC):
    """Abstract base for LLM backends."""

    @abstractmethod
    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate a response from a list of messages.

        Args:
            messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
            max_tokens: Maximum response length.

        Returns:
            The generated text response.
        """

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier."""

    @abstractmethod
    def get_context_size(self) -> int:
        """Return the model's context window size."""

    def supports_tool_use(self) -> bool:
        """Whether this backend supports tool calling."""
        return False

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate with tool calling support.

        Default: ignores tools, returns text-only response.
        Override in backends that support tool calling.
        """
        text = self.generate(messages, max_tokens)
        return LLMResponse(text=text, stop_reason="end_turn")

    # -- Streaming methods (override for real token-level streaming) --

    def generate_stream(
        self, messages: list[dict], max_tokens: int = 1024,
    ) -> Iterator[StreamEvent]:
        """Stream text generation. Yields text_delta events, then response_complete.

        Default: wraps generate() as a single-yield fallback.
        """
        text = self.generate(messages, max_tokens)
        yield StreamEvent(type="text_delta", text=text)
        yield StreamEvent(
            type="response_complete",
            response=LLMResponse(text=text, stop_reason="end_turn"),
        )

    def generate_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> Iterator[StreamEvent]:
        """Stream generation with tool support.

        Yields text_delta events as tokens arrive, then response_complete
        with the final LLMResponse (including any tool_calls).

        Default: wraps generate_with_tools() as a single-yield fallback.
        """
        result = self.generate_with_tools(messages, tools, max_tokens)
        if result.text:
            yield StreamEvent(type="text_delta", text=result.text)
        yield StreamEvent(type="response_complete", response=result)
