"""Core abstractions for benchmark evaluation.

Dataclasses for dataset representation, result tracking, and ABCs
for pluggable adapters and ingestion strategies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore


@dataclass
class BenchmarkSession:
    """A conversation session from a benchmark dataset."""

    session_id: str
    turns: list[dict]  # [{role, content}]
    date: str | None = None


@dataclass
class BenchmarkQuestion:
    """A question from a benchmark dataset with expected answer."""

    id: str
    question: str
    expected_answer: str
    question_type: str  # "temporal-reasoning", "single-hop", etc.
    metadata: dict = field(default_factory=dict)


@dataclass
class BenchmarkDataset:
    """Loaded benchmark dataset ready for evaluation."""

    name: str
    sessions: list[BenchmarkSession]
    questions: list[BenchmarkQuestion]


@dataclass
class AnswerResult:
    """Result for a single evaluated question."""

    question_id: str
    question_type: str
    expected_answer: str
    generated_answer: str
    retrieved_memories: list[dict]
    judge_score: float | None = None
    judge_reasoning: str = ""


@dataclass
class BenchmarkResult:
    """Aggregated results for a full benchmark run."""

    benchmark_name: str
    strategy_name: str
    model_name: str
    overall_accuracy: float
    per_type: dict[str, dict]  # type -> {accuracy, count, sum_score}
    per_question: list[AnswerResult]
    ingestion_stats: dict = field(default_factory=dict)


class IngestStrategy(ABC):
    """ABC for converting benchmark sessions into Cairn memories."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier for reporting."""

    @abstractmethod
    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
    ) -> dict:
        """Ingest benchmark sessions as memories.

        Returns:
            Stats dict with at minimum: {memory_count: int, duration_s: float}
        """


class BenchmarkAdapter(ABC):
    """ABC for loading and adapting a benchmark dataset."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Benchmark identifier for reporting."""

    @abstractmethod
    def load(self, data_dir: str) -> BenchmarkDataset:
        """Load and parse the benchmark dataset from disk.

        Args:
            data_dir: Path to the dataset directory.

        Returns:
            Parsed BenchmarkDataset.
        """

    def get_search_kwargs(self, question: BenchmarkQuestion) -> dict:
        """Return extra kwargs for SearchEngine.search() per question.

        Override for benchmark-specific search tuning (e.g., temporal
        questions might use different limits or modes).
        """
        return {}
