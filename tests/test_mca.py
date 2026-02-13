"""Tests for MCA (Multi-Candidate Assessment) keyword coverage gate."""

from cairn.core.mca import MCAGate, compute_coverage, extract_keywords


# ============================================================
# extract_keywords
# ============================================================

def test_extract_keywords_basic():
    """Extracts content words, lowercased, stopwords removed."""
    kw = extract_keywords("Alice likes pizza and coffee")
    assert "alice" in kw
    assert "likes" in kw
    assert "pizza" in kw
    assert "coffee" in kw
    # Stopwords removed
    assert "and" not in kw


def test_extract_keywords_removes_short_words():
    """Words shorter than 3 characters are excluded."""
    kw = extract_keywords("I am a go to AI")
    # "am", "go", "to", "ai" are all <= 2 chars or stopwords
    assert "am" not in kw
    assert "go" not in kw
    assert "ai" not in kw


def test_extract_keywords_removes_stopwords():
    """Common stopwords are filtered out."""
    kw = extract_keywords("What is the relationship between Alice and Bob?")
    assert "alice" in kw
    assert "bob" in kw
    assert "relationship" in kw
    # Stopwords
    assert "what" not in kw
    assert "the" not in kw
    assert "between" in kw  # not a stopword, >= 3 chars → kept
    assert "and" not in kw


def test_extract_keywords_empty():
    """Empty string returns empty set."""
    assert extract_keywords("") == set()


def test_extract_keywords_only_stopwords():
    """String of only stopwords returns empty set."""
    assert extract_keywords("the a an is are was were") == set()


# ============================================================
# compute_coverage
# ============================================================

def test_coverage_full_overlap():
    """All query keywords found in memory."""
    assert compute_coverage({"alice", "pizza"}, {"alice", "pizza", "coffee"}) == 1.0


def test_coverage_partial_overlap():
    """Some query keywords found."""
    cov = compute_coverage({"alice", "pizza", "coffee"}, {"alice", "tea"})
    assert abs(cov - 1 / 3) < 0.01


def test_coverage_no_overlap():
    """No query keywords found."""
    assert compute_coverage({"alice", "pizza"}, {"bob", "tea"}) == 0.0


def test_coverage_empty_query():
    """Empty query keywords returns 0.0."""
    assert compute_coverage(set(), {"alice", "pizza"}) == 0.0


def test_coverage_empty_memory():
    """Empty memory keywords returns 0.0."""
    assert compute_coverage({"alice"}, set()) == 0.0


# ============================================================
# MCAGate.filter
# ============================================================

def _make_candidates(contents: list[str]) -> list[dict]:
    """Create candidate dicts from content strings."""
    return [{"id": i, "content": c} for i, c in enumerate(contents)]


def test_filter_removes_zero_coverage():
    """Candidates with no keyword overlap are filtered out."""
    gate = MCAGate(threshold=0.1)
    candidates = _make_candidates([
        "Alice likes pizza and coffee",
        "Bob works as an engineer",
        "Alice loves programming",
        "Weather forecast for tomorrow",
    ])

    filtered, stats = gate.filter("Does Alice like pizza?", candidates)

    # "Alice" and "pizza" are query keywords
    # Candidate 0: has alice, pizza → passes
    # Candidate 1: has bob, works, engineer → no overlap → filtered
    # Candidate 2: has alice, loves, programming → partial overlap → passes
    # Candidate 3: has weather, forecast, tomorrow → no overlap → filtered
    assert stats["candidates_in"] == 4
    assert stats["candidates_out"] == 2
    assert stats["filtered_out"] == 2
    assert len(filtered) == 2
    assert filtered[0]["id"] == 0
    assert filtered[1]["id"] == 2


def test_filter_attaches_mca_coverage():
    """Filtered candidates get mca_coverage field."""
    gate = MCAGate(threshold=0.1)
    candidates = _make_candidates(["Alice likes pizza"])

    filtered, _ = gate.filter("Alice pizza", candidates)

    assert len(filtered) == 1
    assert "mca_coverage" in filtered[0]
    assert filtered[0]["mca_coverage"] == 1.0


def test_filter_empty_candidates():
    """Empty candidate list returns empty."""
    gate = MCAGate()
    filtered, stats = gate.filter("test query", [])
    assert filtered == []
    assert stats["candidates_in"] == 0


def test_filter_no_query_keywords_skips():
    """When query has no meaningful keywords, all candidates pass."""
    gate = MCAGate()
    candidates = _make_candidates(["Alice", "Bob", "Charlie"])

    # "is the a" → all stopwords/short words
    filtered, stats = gate.filter("is the a", candidates)

    assert len(filtered) == 3
    assert stats["skipped"] is True


def test_filter_threshold_override():
    """Threshold can be overridden per call."""
    gate = MCAGate(threshold=0.1)
    candidates = _make_candidates([
        "Alice likes pizza and coffee",  # coverage for "alice pizza tea": 2/3 = 0.67
        "Bob drinks tea",  # coverage: 1/3 = 0.33
    ])

    # With high threshold, only the first passes
    filtered, stats = gate.filter("Alice pizza tea", candidates, threshold=0.5)
    assert len(filtered) == 1
    assert filtered[0]["id"] == 0

    # With low threshold, both pass
    filtered2, _ = gate.filter("Alice pizza tea", candidates, threshold=0.1)
    assert len(filtered2) == 2


def test_filter_all_filtered_returns_empty():
    """When all candidates are filtered, returns empty list."""
    gate = MCAGate(threshold=0.5)
    candidates = _make_candidates([
        "Weather forecast sunny",
        "Stock market analysis",
    ])

    filtered, stats = gate.filter("Alice birthday party celebration", candidates)

    assert len(filtered) == 0
    assert stats["candidates_out"] == 0
    assert stats["filtered_out"] == 2


def test_filter_stats_structure():
    """Stats dict has expected keys."""
    gate = MCAGate()
    candidates = _make_candidates(["Alice likes pizza"])
    _, stats = gate.filter("Alice", candidates)

    assert "candidates_in" in stats
    assert "candidates_out" in stats
    assert "filtered_out" in stats
    assert "threshold" in stats
    assert "query_keywords" in stats
    assert "mean_coverage" in stats
    assert "elapsed_ms" in stats
    assert "skipped" in stats
