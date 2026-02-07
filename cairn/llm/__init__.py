"""LLM backend factory. Single place for backend selection."""

from cairn.config import LLMConfig
from cairn.llm.interface import LLMInterface


def get_llm(config: LLMConfig) -> LLMInterface:
    """Return the configured LLM backend."""
    if config.backend == "bedrock":
        from cairn.llm.bedrock import BedrockLLM
        return BedrockLLM(config)
    elif config.backend == "ollama":
        from cairn.llm.ollama import OllamaLLM
        return OllamaLLM(config)
    else:
        raise ValueError(f"Unknown LLM backend: {config.backend}")
