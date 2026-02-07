"""AWS Bedrock LLM implementation via Converse API."""

import logging

import boto3

from cairn.config import LLMConfig
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
        """Generate via Bedrock Converse API."""
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

        response = self._client.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]

    def get_model_name(self) -> str:
        return self.model_id

    def get_context_size(self) -> int:
        return CONTEXT_SIZES.get(self.model_id, 128000)
