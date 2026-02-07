"""Tests for eval metrics. Pure math — no DB, no models, fast.

Every test uses known inputs with hand-computed expected values.
"""

import math

from eval.metrics import (
    compute_all,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


# ── recall@k ────────────────────────────────────────────────────

def test_recall_perfect():
    """All relevant items in top-k → recall = 1.0."""
    retrieved = ["a", "b", "c", "d"]
    relevant = {"a", "b"}
    assert recall_at_k(retrieved, relevant, k=4) == 1.0


def test_recall_partial():
    """Only some relevant items found."""
    retrieved = ["a", "x", "y", "z"]
    relevant = {"a", "b", "c"}
    assert recall_at_k(retrieved, relevant, k=4) == 1 / 3


def test_recall_none():
    """No relevant items in results."""
    retrieved = ["x", "y", "z"]
    relevant = {"a", "b"}
    assert recall_at_k(retrieved, relevant, k=3) == 0.0


def test_recall_empty_relevant():
    """No relevant items defined → vacuously true."""
    assert recall_at_k(["a", "b"], set(), k=2) == 1.0


def test_recall_k_truncates():
    """Only first k results matter."""
    retrieved = ["x", "y", "a", "b"]
    relevant = {"a", "b"}
    assert recall_at_k(retrieved, relevant, k=2) == 0.0
    assert recall_at_k(retrieved, relevant, k=4) == 1.0


# ── precision@k ─────────────────────────────────────────────────

def test_precision_perfect():
    """All top-k results are relevant."""
    retrieved = ["a", "b"]
    relevant = {"a", "b", "c"}
    assert precision_at_k(retrieved, relevant, k=2) == 1.0


def test_precision_half():
    """Half of top-k relevant."""
    retrieved = ["a", "x", "b", "y"]
    relevant = {"a", "b"}
    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_precision_zero_k():
    """k=0 → 0.0 (avoid division by zero)."""
    assert precision_at_k(["a"], {"a"}, k=0) == 0.0


# ── MRR ──────────────────────────────────────────────────────────

def test_mrr_first():
    """First result relevant → MRR = 1.0."""
    assert mrr(["a", "b", "c"], {"a"}) == 1.0


def test_mrr_second():
    """First relevant at position 2 → MRR = 0.5."""
    assert mrr(["x", "a", "b"], {"a"}) == 0.5


def test_mrr_third():
    """First relevant at position 3 → MRR = 1/3."""
    assert abs(mrr(["x", "y", "a"], {"a"}) - 1 / 3) < 1e-10


def test_mrr_none():
    """No relevant results → MRR = 0.0."""
    assert mrr(["x", "y", "z"], {"a"}) == 0.0


def test_mrr_multiple_relevant():
    """Multiple relevant items — only first one counts."""
    assert mrr(["x", "a", "b"], {"a", "b"}) == 0.5


# ── NDCG@k ──────────────────────────────────────────────────────

def test_ndcg_perfect_ranking():
    """Relevant items ranked first → NDCG = 1.0."""
    retrieved = ["a", "b", "x", "y"]
    relevant = {"a", "b"}
    assert abs(ndcg_at_k(retrieved, relevant, k=4) - 1.0) < 1e-10


def test_ndcg_worst_possible():
    """Relevant items ranked last (but within k)."""
    retrieved = ["x", "y", "a", "b"]
    relevant = {"a", "b"}
    # DCG = 1/log2(4) + 1/log2(5) = 0.5 + 0.4307
    # IDCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.6309
    dcg = 1.0 / math.log2(4) + 1.0 / math.log2(5)
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    expected = dcg / idcg
    assert abs(ndcg_at_k(retrieved, relevant, k=4) - expected) < 1e-10


def test_ndcg_no_relevant():
    """No relevant results → NDCG = 0.0."""
    assert ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0


def test_ndcg_empty_relevant():
    """No relevant items defined → vacuously 1.0."""
    assert ndcg_at_k(["x", "y"], set(), k=2) == 1.0


def test_ndcg_single_relevant_at_top():
    """One relevant item at position 1 → NDCG = 1.0."""
    assert abs(ndcg_at_k(["a", "x"], {"a"}, k=2) - 1.0) < 1e-10


def test_ndcg_single_relevant_at_bottom():
    """One relevant at position 2 of k=2."""
    # DCG = 1/log2(3) ≈ 0.6309
    # IDCG = 1/log2(2) = 1.0
    expected = (1.0 / math.log2(3)) / 1.0
    assert abs(ndcg_at_k(["x", "a"], {"a"}, k=2) - expected) < 1e-10


# ── compute_all ──────────────────────────────────────────────────

def test_compute_all_returns_all_metrics():
    """compute_all returns dict with all four metric keys."""
    result = compute_all(["a", "b"], {"a"}, k=2)
    assert set(result.keys()) == {"recall@k", "precision@k", "mrr", "ndcg@k"}


def test_compute_all_values_match_individual():
    """compute_all values match individual function calls."""
    retrieved = ["a", "x", "b", "y", "c"]
    relevant = {"a", "b", "c"}
    k = 5
    result = compute_all(retrieved, relevant, k)
    assert result["recall@k"] == recall_at_k(retrieved, relevant, k)
    assert result["precision@k"] == precision_at_k(retrieved, relevant, k)
    assert result["mrr"] == mrr(retrieved, relevant)
    assert result["ndcg@k"] == ndcg_at_k(retrieved, relevant, k)
