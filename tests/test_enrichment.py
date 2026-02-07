"""Test LLM enrichment pipeline: JSON parsing, override logic, graceful degradation.

Tests use a mock LLM — no real LLM calls. The enricher's job is:
1. Build prompt, call LLM, parse JSON response
2. Validate and normalize fields
3. Return empty dict on any failure (graceful degradation)
"""

import json

from cairn.core.enrichment import Enricher
from cairn.llm.interface import LLMInterface


# ============================================================
# Mock LLM
# ============================================================

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


# ============================================================
# JSON Parsing
# ============================================================

def test_parse_clean_json():
    """Enricher parses a clean JSON response."""
    response = json.dumps({
        "tags": ["python", "testing"],
        "importance": 0.7,
        "memory_type": "learning",
        "summary": "How to test enrichment pipelines.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert result["tags"] == ["python", "testing"]
    assert result["importance"] == 0.7
    assert result["memory_type"] == "learning"
    assert result["summary"] == "How to test enrichment pipelines."


def test_parse_json_with_markdown_fences():
    """Enricher strips markdown code fences."""
    response = '```json\n{"tags": ["docker"], "importance": 0.6, "memory_type": "note", "summary": "Docker stuff."}\n```'
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert result["tags"] == ["docker"]
    assert result["memory_type"] == "note"


def test_parse_json_with_surrounding_text():
    """Enricher finds JSON even with extra text around it."""
    response = 'Here is the analysis:\n{"tags": ["api"], "importance": 0.5, "memory_type": "note", "summary": "API note."}\nDone.'
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert result["tags"] == ["api"]


# ============================================================
# Validation
# ============================================================

def test_importance_clamped():
    """Importance values outside 0-1 are clamped."""
    response = json.dumps({
        "tags": [],
        "importance": 1.5,
        "memory_type": "note",
        "summary": "Over the top.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert result["importance"] == 1.0


def test_invalid_memory_type_excluded():
    """Invalid memory types are dropped from the result."""
    response = json.dumps({
        "tags": ["test"],
        "importance": 0.5,
        "memory_type": "banana",
        "summary": "Invalid type.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert "memory_type" not in result


def test_tags_lowercased():
    """Tags are normalized to lowercase."""
    response = json.dumps({
        "tags": ["Python", "DOCKER", "MiXeD"],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Tags test.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert result["tags"] == ["python", "docker", "mixed"]


def test_tags_limited_to_ten():
    """Tags are capped at 10."""
    response = json.dumps({
        "tags": [f"tag{i}" for i in range(15)],
        "importance": 0.5,
        "memory_type": "note",
        "summary": "Too many tags.",
    })
    enricher = Enricher(MockLLM(response))
    result = enricher.enrich("some content")

    assert len(result["tags"]) == 10


# ============================================================
# Graceful Degradation
# ============================================================

def test_llm_exception_returns_empty_dict():
    """If the LLM throws, enrichment returns empty dict."""
    enricher = Enricher(ExplodingLLM())
    result = enricher.enrich("some content")

    assert result == {}


def test_garbage_response_returns_empty_dict():
    """If the LLM returns non-JSON garbage, enrichment returns empty dict."""
    enricher = Enricher(MockLLM("I don't understand the question."))
    result = enricher.enrich("some content")

    assert result == {}


def test_empty_response_returns_empty_dict():
    """If the LLM returns nothing, enrichment returns empty dict."""
    enricher = Enricher(MockLLM(""))
    result = enricher.enrich("some content")

    assert result == {}


# ============================================================
# Override Logic (tested at MemoryStore level, but logic is documented here)
# ============================================================
# The override logic lives in MemoryStore.store(), not in Enricher.
# These tests document the expected behavior:
#
# - Caller tags -> `tags` column; LLM tags -> `auto_tags` column
# - Caller importance != 0.5 -> caller wins; else LLM wins
# - Caller memory_type != "note" -> caller wins; else LLM wins
# - Summary always comes from LLM
#
# Integration tests for override logic require a database and are
# covered by the end-to-end smoke test on the server.
