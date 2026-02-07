"""LLM-powered enrichment at write time. Single call for tags, importance, type, summary."""

import json
import logging
import re

from cairn.llm.interface import LLMInterface
from cairn.llm.prompts import VALID_MEMORY_TYPES, build_enrichment_messages

logger = logging.getLogger(__name__)


class Enricher:
    """Calls the LLM to enrich memory content. Gracefully degrades on any failure."""

    def __init__(self, llm: LLMInterface):
        self.llm = llm

    def enrich(self, content: str) -> dict:
        """Single LLM call -> parsed enrichment dict.

        Returns dict with keys: tags, importance, memory_type, summary.
        Returns empty dict on ANY failure (LLM down, bad JSON, timeout).
        """
        try:
            messages = build_enrichment_messages(content)
            raw = self.llm.generate(messages, max_tokens=512)
            result = self._parse_response(raw)
            logger.info("Enrichment succeeded: %d tags, importance=%.1f, type=%s",
                        len(result.get("tags", [])), result.get("importance", 0),
                        result.get("memory_type", "unknown"))
            return result
        except Exception:
            logger.warning("Enrichment failed, storing without enrichment", exc_info=True)
            return {}

    def _parse_response(self, raw: str) -> dict:
        """Parse LLM response into enrichment dict. Handles markdown fences."""
        text = raw.strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        # Find JSON object in response
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in response: {text[:200]}")

        data = json.loads(match.group())
        return self._validate(data)

    def _validate(self, data: dict) -> dict:
        """Validate and normalize enrichment fields."""
        result = {}

        # Tags: list of lowercase strings
        tags = data.get("tags", [])
        if isinstance(tags, list):
            result["tags"] = [str(t).lower().strip() for t in tags if t][:10]

        # Importance: float 0.0-1.0
        importance = data.get("importance")
        if importance is not None:
            try:
                importance = float(importance)
                result["importance"] = max(0.0, min(1.0, importance))
            except (TypeError, ValueError):
                pass

        # Memory type: must be valid
        memory_type = data.get("memory_type")
        if memory_type and str(memory_type) in VALID_MEMORY_TYPES:
            result["memory_type"] = str(memory_type)

        # Summary: string
        summary = data.get("summary")
        if summary and isinstance(summary, str):
            result["summary"] = summary.strip()

        return result
