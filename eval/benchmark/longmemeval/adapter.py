"""LongMemEval benchmark adapter."""

from __future__ import annotations

from eval.benchmark.base import BenchmarkAdapter, BenchmarkDataset, BenchmarkQuestion
from eval.benchmark.longmemeval.loader import load_longmemeval


class LongMemEvalAdapter(BenchmarkAdapter):
    """Adapter for LongMemEval (ICLR 2025).

    500 questions across scalable chat histories. Tests:
    - single-session-user, single-session-assistant, single-session-preference
    - multi-session, knowledge-update, temporal-reasoning, abstention
    """

    def __init__(self, scale: str = "longmemeval_s"):
        self.scale = scale

    @property
    def name(self) -> str:
        return self.scale

    def load(self, data_dir: str) -> BenchmarkDataset:
        return load_longmemeval(data_dir, scale=self.scale)

    def get_search_kwargs(self, question: BenchmarkQuestion) -> dict:
        kwargs = {}
        # Temporal and multi-session questions need broader recall
        if question.question_type in ("temporal-reasoning", "multi-session"):
            kwargs["limit"] = 15
        # Knowledge update questions — recency matters
        if question.question_type == "knowledge-update":
            kwargs["limit"] = 15
        return kwargs
