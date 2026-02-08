"""Test query expansion: LLM rewrites search queries for better retrieval.

Tests use mock LLM — no real LLM calls. The SearchEngine's _expand_query():
1. Calls LLM with original query
2. Returns expanded query text
3. Falls back to original query on any failure
"""

from unittest.mock import MagicMock

from cairn.config import LLMCapabilities
from cairn.core.search import SearchEngine

from tests.helpers import ExplodingLLM, MockLLM


# ============================================================
# Happy Path
# ============================================================

def test_query_expansion_happy_path():
    """LLM expands a short query into richer terms."""
    expanded = "docker networking bridge host DNS container communication network config"
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM(expanded),
        capabilities=LLMCapabilities(query_expansion=True),
    )

    result = engine._expand_query("docker networking")
    assert result == expanded


# ============================================================
# LLM Failure
# ============================================================

def test_query_expansion_llm_failure():
    """LLM failure returns original query unchanged."""
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=ExplodingLLM(),
        capabilities=LLMCapabilities(query_expansion=True),
    )

    result = engine._expand_query("docker networking")
    assert result == "docker networking"


# ============================================================
# Flag Off
# ============================================================

def test_query_expansion_flag_off():
    """When flag is off, original query is returned unchanged."""
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM("expanded query terms"),
        capabilities=LLMCapabilities(query_expansion=False),
    )

    result = engine._expand_query("docker networking")
    assert result == "docker networking"


# ============================================================
# Bad Output
# ============================================================

def test_query_expansion_empty_response():
    """Empty LLM response falls back to original query."""
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM(""),
        capabilities=LLMCapabilities(query_expansion=True),
    )

    result = engine._expand_query("docker networking")
    assert result == "docker networking"
