"""LoCoMo benchmark adapter."""

from __future__ import annotations

from pathlib import Path

from eval.benchmark.base import BenchmarkAdapter, BenchmarkDataset, BenchmarkQuestion
from eval.benchmark.locomo.loader import load_locomo


class LoCoMoAdapter(BenchmarkAdapter):
    """Adapter for the LoCoMo benchmark (ACL 2024).

    10 conversations, ~300 turns each. Tests:
    - single-hop, multi-hop, temporal, open-domain, adversarial
    """

    @property
    def name(self) -> str:
        return "locomo"

    def load(self, data_dir: str) -> BenchmarkDataset:
        return load_locomo(data_dir)

    def get_search_kwargs(self, question: BenchmarkQuestion) -> dict:
        kwargs = {}
        # Temporal questions may benefit from more results
        if question.question_type == "temporal":
            kwargs["limit"] = 15
        # Multi-hop needs broader recall
        if question.question_type == "multi-hop":
            kwargs["limit"] = 15
        return kwargs
