"""Search quality metrics. Pure functions, no dependencies.

All functions take:
    retrieved: ordered list of IDs returned by search
    relevant:  set of IDs that are actually relevant

and return a float in [0, 1].
"""

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    """Fraction of relevant items found in the top-k results.

    recall@k = |retrieved[:k] ∩ relevant| / |relevant|
    Primary metric — target is 80%.
    """
    if not relevant:
        return 1.0  # nothing to find = perfect recall
    found = set(retrieved[:k]) & relevant
    return len(found) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    """Fraction of top-k results that are relevant.

    precision@k = |retrieved[:k] ∩ relevant| / k
    """
    if k == 0:
        return 0.0
    found = set(retrieved[:k]) & relevant
    return len(found) / k


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank — 1/rank of the first relevant result.

    MRR = 1 / rank_of_first_relevant
    Returns 0.0 if no relevant result found.
    """
    for i, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    """Normalized Discounted Cumulative Gain at k.

    Uses binary relevance: rel_i = 1 if relevant, 0 otherwise.
    DCG@k  = Σ rel_i / log2(i + 1)  for i in 1..k
    IDCG@k = DCG of the ideal ranking (all relevant items first)
    NDCG@k = DCG@k / IDCG@k
    """
    if not relevant:
        return 1.0

    # DCG of the actual retrieved list
    dcg = 0.0
    for i, item in enumerate(retrieved[:k], start=1):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 1)

    # IDCG: best possible DCG with |relevant| items ranked first
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def compute_all(
    retrieved: list[str], relevant: set[str], k: int = 10,
) -> dict[str, float]:
    """Compute all metrics in one call. Returns a dict keyed by metric name."""
    return {
        "recall@k": recall_at_k(retrieved, relevant, k),
        "precision@k": precision_at_k(retrieved, relevant, k),
        "mrr": mrr(retrieved, relevant),
        "ndcg@k": ndcg_at_k(retrieved, relevant, k),
    }
