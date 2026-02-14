"""Smoke tests for the eval framework. No DB, no models required.

Validates:
- Corpus and query JSON file schemas (by reading JSON directly)
- Metrics on synthetic data (pure math, no imports with DB deps)
- Query relevance judgments reference valid corpus IDs
- Enrichment ground truth schema

These tests run on the host without psycopg or sentence-transformers.
"""

import json
from pathlib import Path

import pytest

from eval.metrics import compute_all, recall_at_k, precision_at_k, mrr, ndcg_at_k

DATA_DIR = Path(__file__).parent.parent / "eval" / "data"

REQUIRED_MEMORY_FIELDS = {"id", "content", "memory_type", "importance", "tags"}
VALID_MEMORY_TYPES = {
    "note", "decision", "rule", "code-snippet", "learning",
    "research", "discussion", "progress", "task", "debug", "design",
}


# ── Helpers ──────────────────────────────────────────────────────

@pytest.fixture
def corpus():
    path = DATA_DIR / "corpus.json"
    if not path.exists():
        pytest.skip("corpus.json not present (gitignored eval data)")
    return json.loads(path.read_text())


@pytest.fixture
def queries():
    path = DATA_DIR / "queries.json"
    if not path.exists():
        pytest.skip("queries.json not present (gitignored eval data)")
    return json.loads(path.read_text())


# ── Corpus schema validation ─────────────────────────────────────

class TestCorpusSchema:
    """Validate corpus.json structure."""

    def test_has_memories(self, corpus):
        assert "memories" in corpus
        assert len(corpus["memories"]) > 0

    def test_has_metadata(self, corpus):
        assert "metadata" in corpus
        assert "version" in corpus["metadata"]

    def test_all_memories_have_required_fields(self, corpus):
        for mem in corpus["memories"]:
            missing = REQUIRED_MEMORY_FIELDS - set(mem.keys())
            assert not missing, f"Memory {mem.get('id', '?')} missing: {missing}"

    def test_memory_ids_are_unique(self, corpus):
        ids = [m["id"] for m in corpus["memories"]]
        assert len(ids) == len(set(ids)), "Duplicate memory IDs found"

    def test_memory_types_are_valid(self, corpus):
        for mem in corpus["memories"]:
            assert mem["memory_type"] in VALID_MEMORY_TYPES, (
                f"Memory {mem['id']} has invalid type: {mem['memory_type']}"
            )

    def test_importance_in_range(self, corpus):
        for mem in corpus["memories"]:
            assert 0.0 <= mem["importance"] <= 1.0, (
                f"Memory {mem['id']} importance out of range: {mem['importance']}"
            )


# ── Query schema validation ──────────────────────────────────────

class TestQuerySchema:
    """Validate queries.json structure."""

    def test_has_queries(self, queries):
        assert "queries" in queries
        assert len(queries["queries"]) > 0

    def test_all_queries_have_required_fields(self, queries):
        for q in queries["queries"]:
            assert "id" in q, "Query missing 'id'"
            assert "query" in q, "Query missing 'query'"
            assert "relevant" in q, "Query missing 'relevant'"

    def test_all_queries_have_relevant(self, queries):
        for q in queries["queries"]:
            assert len(q["relevant"]) > 0, f"Query {q['id']} has no relevant memories"

    def test_query_ids_are_unique(self, queries):
        ids = [q["id"] for q in queries["queries"]]
        assert len(ids) == len(set(ids)), "Duplicate query IDs found"

    def test_relevant_ids_exist_in_corpus(self, corpus, queries):
        """Every relevant ID in queries should reference a memory in the corpus."""
        corpus_ids = {m["id"] for m in corpus["memories"]}
        for q in queries["queries"]:
            orphans = set(q["relevant"]) - corpus_ids
            assert not orphans, (
                f"Query {q['id']} references non-existent memories: {orphans}"
            )


# ── Metrics on synthetic data ────────────────────────────────────

class TestMetricsSynthetic:
    """Run metrics on known synthetic data to verify end-to-end."""

    def test_perfect_retrieval(self):
        """All relevant items returned first."""
        retrieved = ["m01", "m02", "m03", "x1", "x2"]
        relevant = {"m01", "m02", "m03"}
        result = compute_all(retrieved, relevant, k=5)
        assert result["recall@k"] == 1.0
        assert result["precision@k"] == 3 / 5
        assert result["mrr"] == 1.0
        assert abs(result["ndcg@k"] - 1.0) < 1e-10

    def test_no_relevant_found(self):
        """None of the relevant items in results."""
        retrieved = ["x1", "x2", "x3"]
        relevant = {"m01", "m02"}
        result = compute_all(retrieved, relevant, k=3)
        assert result["recall@k"] == 0.0
        assert result["precision@k"] == 0.0
        assert result["mrr"] == 0.0
        assert result["ndcg@k"] == 0.0

    def test_partial_retrieval(self):
        """Some relevant, some not."""
        retrieved = ["m01", "x1", "m02", "x2", "x3"]
        relevant = {"m01", "m02", "m03"}
        result = compute_all(retrieved, relevant, k=5)
        assert result["recall@k"] == 2 / 3
        assert result["precision@k"] == 2 / 5
        assert result["mrr"] == 1.0  # m01 at position 1

    def test_metrics_bounded(self):
        """All metrics should be in [0, 1]."""
        retrieved = ["a", "b", "c", "d", "e"]
        relevant = {"b", "d", "f"}
        result = compute_all(retrieved, relevant, k=5)
        for name, value in result.items():
            assert 0.0 <= value <= 1.0, f"{name} = {value} out of bounds"


# ── Enrichment ground truth schema ──────────────────────────────

class TestEnrichmentGroundTruth:
    """Validate enrichment_ground_truth.json."""

    @pytest.fixture
    def ground_truth(self):
        path = DATA_DIR / "enrichment_ground_truth.json"
        if not path.exists():
            pytest.skip("enrichment_ground_truth.json not present (gitignored eval data)")
        return json.loads(path.read_text())

    def test_has_samples(self, ground_truth):
        assert "samples" in ground_truth
        assert len(ground_truth["samples"]) > 0

    def test_samples_have_required_fields(self, ground_truth):
        for i, sample in enumerate(ground_truth["samples"]):
            assert "content" in sample, f"Sample {i} missing 'content'"
            assert "expected_tags" in sample, f"Sample {i} missing 'expected_tags'"
            assert "importance_range" in sample, f"Sample {i} missing 'importance_range'"
            assert "expected_types" in sample, f"Sample {i} missing 'expected_types'"

    def test_importance_ranges_valid(self, ground_truth):
        for i, sample in enumerate(ground_truth["samples"]):
            low, high = sample["importance_range"]
            assert 0.0 <= low <= high <= 1.0, (
                f"Sample {i} has invalid importance range: [{low}, {high}]"
            )

    def test_expected_types_are_valid(self, ground_truth):
        for i, sample in enumerate(ground_truth["samples"]):
            for t in sample["expected_types"]:
                assert t in VALID_MEMORY_TYPES, (
                    f"Sample {i} has invalid expected type: {t}"
                )
