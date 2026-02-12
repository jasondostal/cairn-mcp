"""Tests for spreading activation engine.

Tests the algorithm logic without a real database — uses a mock graph.
"""

import math
from cairn.core.activation import (
    ActivationEngine,
    _sigmoid,
    GAMMA,
    THETA,
    MIN_ACTIVATION,
)


def test_sigmoid_at_threshold():
    """Sigmoid at theta should return 0.5."""
    assert abs(_sigmoid(THETA) - 0.5) < 1e-6


def test_sigmoid_above_threshold():
    """Values above theta should return > 0.5."""
    assert _sigmoid(THETA + 0.1) > 0.5


def test_sigmoid_below_threshold():
    """Values below theta should return < 0.5."""
    assert _sigmoid(THETA - 0.1) < 0.5


def test_sigmoid_extreme_positive():
    """Very high input should approach 1.0."""
    assert _sigmoid(10.0) > 0.99


def test_sigmoid_extreme_negative():
    """Very low input should approach 0.0."""
    assert _sigmoid(-10.0) < 0.01


class FakeDB:
    """Minimal mock for Database that returns pre-configured results."""

    def __init__(self, nodes: list[dict], edges: list[dict]):
        self._nodes = nodes
        self._edges = edges
        self._call_count = 0

    def execute(self, query: str, params=None):
        self._call_count += 1
        if "FROM memories WHERE" in query:
            return self._nodes
        if "FROM memory_relations" in query:
            return self._edges
        return []

    def execute_one(self, query, params=None):
        return None


def test_activate_with_linear_graph():
    """Activation should propagate through a linear chain: A -> B -> C."""
    nodes = [{"id": 1}, {"id": 2}, {"id": 3}]
    edges = [
        {"source_id": 1, "target_id": 2, "weight": 1.0},
        {"source_id": 2, "target_id": 3, "weight": 1.0},
    ]
    db = FakeDB(nodes, edges)
    engine = ActivationEngine(db)

    result = engine.activate(
        anchor_ids=[1],
        anchor_scores={1: 1.0},
        project_id=None,
    )

    # Node 1 should be activated (it's the anchor)
    assert result.get(1, 0) > MIN_ACTIVATION
    # Node 2 should get some activation from node 1
    assert result.get(2, 0) > MIN_ACTIVATION
    # Node 3 might get activation depending on iterations
    # (may or may not exceed threshold)


def test_activate_no_anchors():
    """Empty anchors should return empty result."""
    engine = ActivationEngine(FakeDB([], []))
    result = engine.activate([], {}, project_id=None)
    assert result == {}


def test_activate_disconnected_node():
    """Disconnected nodes should only retain self-activation if anchored."""
    nodes = [{"id": 1}, {"id": 2}]  # No edges between them
    edges = []
    db = FakeDB(nodes, edges)
    engine = ActivationEngine(db)

    result = engine.activate(
        anchor_ids=[1],
        anchor_scores={1: 1.0},
        project_id=None,
    )

    # Node 1 is anchored, should be activated
    assert result.get(1, 0) > MIN_ACTIVATION
    # Node 2 has no incoming edges and isn't anchored
    # It should have zero or near-zero activation
    assert result.get(2, 0) < 0.1


def test_fan_effect():
    """Hub nodes should spread activation thinner (fan effect).

    A -> B, A -> C, A -> D: B, C, D each get 1/3 of A's activation
    vs A -> B only: B gets all of A's activation.
    """
    # Graph with hub A (id=1) -> B(2), C(3), D(4)
    nodes_hub = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
    edges_hub = [
        {"source_id": 1, "target_id": 2, "weight": 1.0},
        {"source_id": 1, "target_id": 3, "weight": 1.0},
        {"source_id": 1, "target_id": 4, "weight": 1.0},
    ]
    db_hub = FakeDB(nodes_hub, edges_hub)
    engine_hub = ActivationEngine(db_hub)
    result_hub = engine_hub.activate([1], {1: 1.0})

    # Graph with single edge A(1) -> B(2)
    nodes_single = [{"id": 1}, {"id": 2}]
    edges_single = [
        {"source_id": 1, "target_id": 2, "weight": 1.0},
    ]
    db_single = FakeDB(nodes_single, edges_single)
    engine_single = ActivationEngine(db_single)
    result_single = engine_single.activate([1], {1: 1.0})

    # B in the single-edge graph should have higher activation than
    # B in the hub graph (fan effect)
    assert result_single.get(2, 0) >= result_hub.get(2, 0)


def test_pagerank_simple():
    """PageRank on a simple graph should produce valid scores."""
    nodes = {1, 2, 3}
    edges = {
        1: [(2, 1.0)],
        2: [(3, 1.0)],
        3: [(1, 1.0)],
    }

    pr = ActivationEngine.compute_pagerank(nodes, edges)

    # All nodes in a cycle should have similar PageRank
    assert len(pr) == 3
    values = list(pr.values())
    assert all(v > 0 for v in values)
    # In a perfectly balanced cycle, all should be equal
    assert abs(values[0] - values[1]) < 0.01
    assert abs(values[1] - values[2]) < 0.01


def test_pagerank_empty_graph():
    """PageRank on empty graph returns empty dict."""
    pr = ActivationEngine.compute_pagerank(set(), {})
    assert pr == {}


def test_pagerank_sink_node():
    """Sink nodes (no outgoing edges) should still get PageRank."""
    nodes = {1, 2}
    edges = {
        1: [(2, 1.0)],  # 1 -> 2, but 2 goes nowhere
    }
    pr = ActivationEngine.compute_pagerank(nodes, edges)

    assert pr[2] > 0  # Sink should have rank
    assert pr[1] > 0  # Source should also have rank (from random jump)


def test_cache_invalidation():
    """Cache should be clearable."""
    engine = ActivationEngine(FakeDB([], []))
    engine._graph_cache[None] = {"nodes": set(), "edges": {}, "fan_out": {}}
    assert None in engine._graph_cache

    engine.invalidate_cache()
    assert len(engine._graph_cache) == 0
