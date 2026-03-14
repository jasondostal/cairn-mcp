"""Tests for cairn.core.tool_ops — shared tool operations.

Verifies that budgeted_search, budgeted_recall, validate_modify_inputs, and
budgeted_discover_patterns produce correct results with budget caps, event
emission, and validation.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

from cairn.core.tool_ops import (
    budgeted_discover_patterns,
    budgeted_recall,
    budgeted_search,
    validate_modify_inputs,
)


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


@dataclass
class MockBudgetConfig:
    search: int = 0
    recall: int = 0
    insights: int = 0


@dataclass
class MockConfig:
    budget: MockBudgetConfig = None

    def __post_init__(self):
        if self.budget is None:
            self.budget = MockBudgetConfig()


def _make_svc(**overrides):
    svc = MagicMock()
    svc.config = MockConfig()
    svc.event_bus = None
    for key, val in overrides.items():
        setattr(svc, key, val)
    return svc


# ---------------------------------------------------------------------------
# budgeted_search
# ---------------------------------------------------------------------------


class TestBudgetedSearch:
    def test_basic_search_returns_results_and_confidence(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = [
            {"id": 1, "summary": "First result", "score": 0.9},
            {"id": 2, "summary": "Second result", "score": 0.7},
        ]
        svc.search_engine.assess_confidence.return_value = 0.85

        result = budgeted_search(svc, query="test query")

        assert "error" not in result
        assert len(result["results"]) == 2
        assert result["confidence"] == 0.85
        svc.search_engine.search.assert_called_once()

    def test_search_with_all_filters(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = []
        svc.search_engine.assess_confidence.return_value = None

        budgeted_search(
            svc, query="test", project="cairn",
            memory_type="decision", search_mode="keyword",
            limit=5, as_of="2026-01-01", event_after="2026-01-01",
            event_before="2026-03-01", ephemeral=False,
        )

        kwargs = svc.search_engine.search.call_args.kwargs
        assert kwargs["project"] == "cairn"
        assert kwargs["memory_type"] == "decision"
        assert kwargs["search_mode"] == "keyword"
        assert kwargs["limit"] == 5

    def test_search_invalid_mode_returns_error(self):
        svc = _make_svc()
        result = budgeted_search(svc, query="test", search_mode="invalid")
        assert "error" in result
        assert "invalid search_mode" in result["error"]

    def test_search_emits_event(self):
        bus = MagicMock()
        svc = _make_svc(event_bus=bus)
        svc.search_engine.search.return_value = [
            {"id": 1, "summary": "Found"},
        ]
        svc.search_engine.assess_confidence.return_value = None

        budgeted_search(svc, query="deploy command", source="chat")

        bus.emit.assert_called_once()
        call_args = bus.emit.call_args
        assert call_args[0][0] == "search.executed"
        assert call_args[1]["payload"]["source"] == "chat"
        assert call_args[1]["payload"]["query"] == "deploy command"

    def test_search_emits_event_without_source(self):
        bus = MagicMock()
        svc = _make_svc(event_bus=bus)
        svc.search_engine.search.return_value = [
            {"id": 1, "summary": "Found"},
        ]
        svc.search_engine.assess_confidence.return_value = None

        budgeted_search(svc, query="test")

        payload = bus.emit.call_args[1]["payload"]
        assert "source" not in payload

    def test_search_no_event_when_no_results(self):
        bus = MagicMock()
        svc = _make_svc(event_bus=bus)
        svc.search_engine.search.return_value = []
        svc.search_engine.assess_confidence.return_value = None

        budgeted_search(svc, query="nothing")

        bus.emit.assert_not_called()

    def test_search_budget_caps_results(self):
        svc = _make_svc()
        # Enable budget cap (very small)
        svc.config.budget.search = 10
        svc.search_engine.search.return_value = [
            {"id": i, "summary": "A" * 500} for i in range(20)
        ]
        svc.search_engine.assess_confidence.return_value = None

        result = budgeted_search(svc, query="test")

        # Should have fewer results than 20 due to budget
        assert len(result["results"]) < 20

    def test_search_confidence_none_when_disabled(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = []
        svc.search_engine.assess_confidence.return_value = None

        result = budgeted_search(svc, query="test")

        assert result["confidence"] is None

    def test_search_limits_capped_at_20(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = []
        svc.search_engine.assess_confidence.return_value = None

        budgeted_search(svc, query="test", limit=100)

        kwargs = svc.search_engine.search.call_args.kwargs
        assert kwargs["limit"] == 20


# ---------------------------------------------------------------------------
# budgeted_recall
# ---------------------------------------------------------------------------


class TestBudgetedRecall:
    def test_basic_recall(self):
        svc = _make_svc()
        svc.memory_store.recall.return_value = [
            {"id": 1, "content": "Full memory content"},
            {"id": 2, "content": "Another memory"},
        ]

        result = budgeted_recall(svc, ids=[1, 2])

        assert "error" not in result
        assert len(result["results"]) == 2
        svc.memory_store.recall.assert_called_once_with([1, 2])

    def test_recall_empty_ids_returns_error(self):
        svc = _make_svc()
        result = budgeted_recall(svc, ids=[])
        assert "error" in result
        assert "empty" in result["error"]

    def test_recall_too_many_ids_returns_error(self):
        svc = _make_svc()
        result = budgeted_recall(svc, ids=list(range(100)))
        assert "error" in result
        assert "Maximum" in result["error"]

    def test_recall_emits_event(self):
        bus = MagicMock()
        svc = _make_svc(event_bus=bus)
        svc.memory_store.recall.return_value = [
            {"id": 1, "content": "content"},
        ]

        budgeted_recall(svc, ids=[1], source="chat")

        bus.emit.assert_called_once()
        call_args = bus.emit.call_args
        assert call_args[0][0] == "memory.recalled"
        assert call_args[1]["payload"]["source"] == "chat"

    def test_recall_emits_event_without_source(self):
        bus = MagicMock()
        svc = _make_svc(event_bus=bus)
        svc.memory_store.recall.return_value = [
            {"id": 1, "content": "content"},
        ]

        budgeted_recall(svc, ids=[1])

        payload = bus.emit.call_args[1]["payload"]
        assert "source" not in payload

    def test_recall_budget_caps_content(self):
        svc = _make_svc()
        svc.config.budget.recall = 10  # Very small budget
        svc.memory_store.recall.return_value = [
            {"id": i, "content": "X" * 1000} for i in range(10)
        ]

        result = budgeted_recall(svc, ids=list(range(10)))

        # Should have fewer results due to budget
        assert len(result["results"]) < 10


# ---------------------------------------------------------------------------
# validate_modify_inputs
# ---------------------------------------------------------------------------


class TestValidateModifyInputs:
    def test_valid_update(self):
        assert validate_modify_inputs("update") is None

    def test_valid_inactivate(self):
        assert validate_modify_inputs("inactivate") is None

    def test_valid_reactivate(self):
        assert validate_modify_inputs("reactivate") is None

    def test_invalid_action(self):
        err = validate_modify_inputs("delete")
        assert err is not None
        assert "invalid action" in err

    def test_content_too_long(self):
        err = validate_modify_inputs("update", content="x" * 500_001)
        assert err is not None
        assert "character limit" in err

    def test_invalid_memory_type(self):
        err = validate_modify_inputs("update", memory_type="invalid_type")
        assert err is not None
        assert "invalid memory_type" in err

    def test_importance_too_low(self):
        err = validate_modify_inputs("update", importance=-0.1)
        assert err is not None
        assert "importance" in err

    def test_importance_too_high(self):
        err = validate_modify_inputs("update", importance=1.5)
        assert err is not None
        assert "importance" in err

    def test_valid_with_all_fields(self):
        err = validate_modify_inputs(
            "update", content="new content",
            memory_type="decision", importance=0.8,
        )
        assert err is None


# ---------------------------------------------------------------------------
# budgeted_discover_patterns
# ---------------------------------------------------------------------------


class TestBudgetedDiscoverPatterns:
    def test_returns_cached_when_not_stale(self):
        svc = _make_svc()
        svc.cluster_engine.is_stale.return_value = False
        svc.cluster_engine.get_clusters.return_value = [
            {"id": 1, "summary": "Testing patterns", "size": 5},
        ]
        svc.cluster_engine.get_last_run.return_value = {"created_at": "2026-01-01T00:00:00"}

        result = budgeted_discover_patterns(svc, project="cairn")

        assert result["status"] == "cached"
        assert result["cluster_count"] == 1
        svc.cluster_engine.run_clustering.assert_not_called()

    def test_reclusters_when_stale(self):
        svc = _make_svc()
        svc.cluster_engine.is_stale.return_value = True
        svc.cluster_engine.run_clustering.return_value = {}
        svc.cluster_engine.get_clusters.return_value = []
        svc.cluster_engine.get_last_run.return_value = None

        result = budgeted_discover_patterns(svc)

        assert result["status"] == "reclustered"
        svc.cluster_engine.run_clustering.assert_called_once()

    def test_includes_labeling_warning(self):
        svc = _make_svc()
        svc.cluster_engine.is_stale.return_value = True
        svc.cluster_engine.run_clustering.return_value = {"labeling_error": "LLM timeout"}
        svc.cluster_engine.get_clusters.return_value = []
        svc.cluster_engine.get_last_run.return_value = None

        result = budgeted_discover_patterns(svc)

        assert result["labeling_warning"] == "LLM timeout"

    def test_budget_caps_clusters(self):
        svc = _make_svc()
        svc.config.budget.insights = 10  # Very small
        svc.cluster_engine.is_stale.return_value = False
        svc.cluster_engine.get_clusters.return_value = [
            {"id": i, "summary": "A" * 500, "size": 3} for i in range(20)
        ]
        svc.cluster_engine.get_last_run.return_value = None

        result = budgeted_discover_patterns(svc)

        assert result["cluster_count"] < 20
        assert "_overflow" in result
