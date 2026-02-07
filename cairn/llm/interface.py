"""LLM interface ABC. Implementations must provide generate()."""

from abc import ABC, abstractmethod


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
