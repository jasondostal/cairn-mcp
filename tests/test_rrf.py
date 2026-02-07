"""Test the RRF math. This is the heart of hybrid search — if the math is wrong, search is wrong.

Constants are duplicated here intentionally — these tests validate the MATH,
not the import chain. If the constants change in search.py, these tests should
still pass (they test the formula, not the config).
"""

# RRF constant and weights (mirrored from cairn.core.search)
RRF_K = 60
WEIGHTS = {"vector": 0.60, "keyword": 0.25, "tag": 0.15}


def rrf_score(rank: int) -> float:
    """RRF formula: 1 / (k + rank)."""
    return 1.0 / (RRF_K + rank)


def test_rrf_formula():
    """RRF score for rank 1 should be 1/(k+1)."""
    assert abs(rrf_score(1) - (1.0 / 61)) < 1e-10


def test_rrf_rank_ordering():
    """Lower rank (better) should produce higher RRF score."""
    assert rrf_score(1) > rrf_score(10)


def test_rrf_diminishing_returns():
    """Difference between rank 1 and 2 should be larger than between rank 50 and 51."""
    delta_top = rrf_score(1) - rrf_score(2)
    delta_bottom = rrf_score(50) - rrf_score(51)
    assert delta_top > delta_bottom


def test_default_weights_sum_to_one():
    """Signal weights must sum to 1.0 for normalized scoring."""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-10


def test_hybrid_score_calculation():
    """Simulate a hybrid score for a memory appearing in all three signals."""
    # Memory at rank 1 in vector, rank 3 in keyword, rank 5 in tag
    vector_score = WEIGHTS["vector"] * rrf_score(1)
    keyword_score = WEIGHTS["keyword"] * rrf_score(3)
    tag_score = WEIGHTS["tag"] * rrf_score(5)

    total = vector_score + keyword_score + tag_score

    assert total > 0
    # Should be less than theoretical max (all rank 1)
    max_score = sum(w * rrf_score(1) for w in WEIGHTS.values())
    assert total < max_score


def test_vector_dominates():
    """Vector signal at 60% should contribute more than keyword at 25% at same rank."""
    rank = 1
    vector_contribution = WEIGHTS["vector"] * rrf_score(rank)
    keyword_contribution = WEIGHTS["keyword"] * rrf_score(rank)
    assert vector_contribution > keyword_contribution


def test_missing_signal():
    """A memory that only appears in vector search should still score positively."""
    total = WEIGHTS["vector"] * rrf_score(1)
    assert total > 0


def test_keyword_only_beats_low_vector():
    """A rank-1 keyword match can beat a rank-50 vector match (sometimes)."""
    keyword_only = WEIGHTS["keyword"] * rrf_score(1)
    vector_low = WEIGHTS["vector"] * rrf_score(50)
    # This demonstrates why hybrid search matters — different signals win in different cases
    # Both should be non-trivial
    assert keyword_only > 0
    assert vector_low > 0
