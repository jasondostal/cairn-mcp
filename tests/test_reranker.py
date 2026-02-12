"""Tests for cross-encoder reranker.

Tests the Reranker class logic without loading the actual model
(uses monkeypatching to mock the CrossEncoder).
"""

from unittest.mock import MagicMock, patch

from cairn.core.reranker import Reranker


def _make_candidates(n: int) -> list[dict]:
    """Create N dummy candidates with id and content."""
    return [
        {"id": i, "content": f"Memory content {i}"}
        for i in range(1, n + 1)
    ]


def test_skip_when_pool_lte_limit():
    """When candidates <= limit, reranker returns them as-is (no model call)."""
    reranker = Reranker()
    candidates = _make_candidates(5)
    result = reranker.rerank("test query", candidates, limit=10)
    assert result == candidates
    assert reranker._model is None  # Model never loaded


def test_empty_candidates():
    """Empty candidate list returns empty."""
    reranker = Reranker()
    result = reranker.rerank("test query", [], limit=10)
    assert result == []


def test_rerank_selects_top_k():
    """Reranker should select top-k by cross-encoder score."""
    reranker = Reranker()

    # Mock the cross-encoder: assign scores inversely (last candidate = highest score)
    mock_model = MagicMock()
    candidates = _make_candidates(10)
    # Scores: id 1 -> 0.1, id 2 -> 0.2, ..., id 10 -> 1.0
    mock_model.predict.return_value = [i * 0.1 for i in range(1, 11)]
    reranker._model = mock_model

    result = reranker.rerank("test query", candidates, limit=3)

    assert len(result) == 3
    # Top 3 should be ids 10, 9, 8 (highest scores)
    assert result[0]["id"] == 10
    assert result[1]["id"] == 9
    assert result[2]["id"] == 8


def test_rerank_attaches_scores():
    """Reranker should attach rerank_score to each candidate."""
    reranker = Reranker()

    mock_model = MagicMock()
    candidates = _make_candidates(5)
    mock_model.predict.return_value = [0.9, 0.1, 0.5, 0.3, 0.7]
    reranker._model = mock_model

    result = reranker.rerank("test query", candidates, limit=3)

    for r in result:
        assert "rerank_score" in r
        assert isinstance(r["rerank_score"], float)

    # First result should have the highest score
    assert result[0]["rerank_score"] == 0.9


def test_rerank_fallback_on_predict_error():
    """If model.predict raises, return first N candidates as fallback."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.side_effect = RuntimeError("CUDA OOM")
    reranker._model = mock_model

    candidates = _make_candidates(10)
    result = reranker.rerank("test query", candidates, limit=3)

    assert len(result) == 3
    # Should be the first 3 candidates (no reranking applied)
    assert result[0]["id"] == 1
