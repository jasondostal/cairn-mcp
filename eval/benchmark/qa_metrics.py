"""QA accuracy metrics and per-type aggregation.

Pure functions — no LLM calls, no I/O.
"""

from __future__ import annotations

from eval.benchmark.base import AnswerResult


def compute_accuracy(results: list[AnswerResult]) -> float:
    """Overall accuracy from judge scores. Skips unscored results."""
    scored = [r for r in results if r.judge_score is not None]
    if not scored:
        return 0.0
    return sum(r.judge_score for r in scored) / len(scored)


def compute_per_type(results: list[AnswerResult]) -> dict[str, dict]:
    """Per-question-type breakdown.

    Returns:
        {type_name: {accuracy: float, count: int, sum_score: float}}
    """
    buckets: dict[str, list[AnswerResult]] = {}
    for r in results:
        buckets.setdefault(r.question_type, []).append(r)

    per_type = {}
    for qtype, items in sorted(buckets.items()):
        scored = [r for r in items if r.judge_score is not None]
        total_score = sum(r.judge_score for r in scored)
        per_type[qtype] = {
            "accuracy": total_score / len(scored) if scored else 0.0,
            "count": len(items),
            "scored": len(scored),
            "sum_score": total_score,
        }
    return per_type


def compute_f1(prediction: str, reference: str) -> float:
    """Token-level F1 between prediction and reference strings.

    Used as a secondary metric alongside judge scores.
    """
    pred_tokens = set(prediction.lower().split())
    ref_tokens = set(reference.lower().split())

    if not pred_tokens or not ref_tokens:
        return 0.0

    common = pred_tokens & ref_tokens
    if not common:
        return 0.0

    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)
