"""Shared test helpers for Cairn tests."""

from cairn.llm.interface import LLMInterface


class MockLLM(LLMInterface):
    """Returns a canned response for testing."""

    def __init__(self, response: str = ""):
        self._response = response

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        return self._response

    def get_model_name(self) -> str:
        return "mock"

    def get_context_size(self) -> int:
        return 4096


class ExplodingLLM(LLMInterface):
    """Always raises an exception."""

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        raise ConnectionError("LLM is down")

    def get_model_name(self) -> str:
        return "exploding"

    def get_context_size(self) -> int:
        return 0
