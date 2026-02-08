"""Test confidence gating: LLM assesses whether search results answer the query.

Tests use mock LLM — no real calls. SearchEngine.assess_confidence():
1. Calls LLM with query + results
2. Returns confidence assessment dict
3. Returns None when disabled/unavailable/fails
"""

import json
from unittest.mock import MagicMock

from cairn.config import LLMCapabilities
from cairn.core.search import SearchEngine

from tests.helpers import ExplodingLLM, MockLLM


def _make_results(n: int = 3) -> list[dict]:
    """Build fake search results."""
    return [
        {
            "id": i + 1,
            "summary": f"Result {i + 1} about Docker containers.",
            "score": 0.9 - (i * 0.1),
            "memory_type": "note",
        }
        for i in range(n)
    ]


# ============================================================
# High Confidence
# ============================================================

def test_confidence_high():
    """LLM returns high confidence for relevant results."""
    response = json.dumps({
        "confidence": 0.92,
        "assessment": "Results directly address Docker networking query.",
        "best_match_id": 1,
        "irrelevant_ids": [],
    })
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM(response),
        capabilities=LLMCapabilities(confidence_gating=True),
    )

    result = engine.assess_confidence("docker networking", _make_results())

    assert result is not None
    assert result["confidence"] == 0.92
    assert result["best_match_id"] == 1


# ============================================================
# Low Confidence
# ============================================================

def test_confidence_low():
    """LLM returns low confidence for irrelevant results."""
    response = json.dumps({
        "confidence": 0.2,
        "assessment": "Results are about Python, not Docker.",
        "best_match_id": None,
        "irrelevant_ids": [1, 2, 3],
    })
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM(response),
        capabilities=LLMCapabilities(confidence_gating=True),
    )

    result = engine.assess_confidence("docker networking", _make_results())

    assert result is not None
    assert result["confidence"] == 0.2
    assert len(result["irrelevant_ids"]) == 3


# ============================================================
# Flag Off
# ============================================================

def test_confidence_flag_off():
    """When flag is off, returns None (backward compatible)."""
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=MockLLM("should not be called"),
        capabilities=LLMCapabilities(confidence_gating=False),
    )

    result = engine.assess_confidence("docker networking", _make_results())
    assert result is None


# ============================================================
# LLM Failure
# ============================================================

def test_confidence_llm_failure():
    """LLM failure returns None."""
    engine = SearchEngine(
        MagicMock(), MagicMock(),
        llm=ExplodingLLM(),
        capabilities=LLMCapabilities(confidence_gating=True),
    )

    result = engine.assess_confidence("docker networking", _make_results())
    assert result is None
