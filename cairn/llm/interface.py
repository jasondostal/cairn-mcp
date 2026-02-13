"""LLM interface ABC. Implementations must provide generate()."""

from abc import ABC, abstractmethod
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
