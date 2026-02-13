"""Spreading activation over the memory graph.

Start from anchor nodes matching the query, propagate activation through
graph edges for T iterations, and surface structurally-connected memories
that embedding similarity alone would never find.

Algorithm:
  1. ANCHOR: Find top-N nodes via vector + keyword signals (reuses search infra)
  2. INIT:   a_i = similarity if anchor, else 0
  3. PROPAGATE (T iterations):
     For each node: u_i = (1-δ)·a_i + Σ_{j→i} S·w_ji·a_j / fan(j)
     INHIBIT: top-K nodes suppress lower activations (lateral inhibition)
     FIRE:    a_i = sigmoid(u_i, γ, θ)
  4. RETURN: {node_id: activation} for all a_i > ε

Parameters:
  - δ = 0.5  (external vs propagated balance)
  - S = 0.8  (spread factor)
  - T = 3    (propagation iterations)
  - γ = 5.0  (sigmoid steepness)
  - θ = 0.5  (sigmoid threshold)
  - β = 0.15 (lateral inhibition strength)
  - top_k_inhibit = 7 (number of winners for inhibition)
  - ε = 0.01 (minimum activation to return)
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Activation parameters
DELTA = 0.5       # external vs propagated balance
SPREAD = 0.8      # spread factor
ITERATIONS = 3    # propagation rounds
GAMMA = 5.0       # sigmoid steepness
THETA = 0.5       # sigmoid threshold
BETA = 0.15       # lateral inhibition strength
TOP_K_INHIBIT = 7 # number of winner nodes for inhibition
MIN_ACTIVATION = 0.01  # threshold to include in results
MAX_GRAPH_NODES = 10_000  # cap on graph size


def _sigmoid(x: float, gamma: float = GAMMA, theta: float = THETA) -> float:
    """Sigmoid activation function."""
    z = gamma * (x - theta)
    # Clamp to avoid overflow
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


class ActivationEngine:
    """Spreading activation over the memory relation graph.

    Loads the project subgraph lazily, propagates activation from anchor nodes,
    and returns activation values as a scoring signal for RRF.
    """

    def __init__(self, db: Database):
        self.db = db
        self._graph_cache: dict[int | None, dict] = {}  # project_id -> graph

    def activate(
        self,
        anchor_ids: list[int],
        anchor_scores: dict[int, float],
        project_id: int | None = None,
    ) -> dict[int, float]:
        """Run spreading activation from anchor nodes.

        Args:
            anchor_ids: Memory IDs to start activation from (from search).
            anchor_scores: Initial activation values (e.g. vector similarity).
            project_id: Project to scope the graph to.

        Returns:
            Mapping of memory_id -> activation value (filtered by MIN_ACTIVATION).
        """
        if not anchor_ids:
            return {}

        graph = self._load_graph(project_id)
        if not graph["nodes"]:
            return {}

        nodes = graph["nodes"]  # set of node IDs
        edges = graph["edges"]  # source_id -> [(target_id, weight)]
        fan_out = graph["fan_out"]  # node_id -> out-degree

        # 1. Initialize activation
        activation = {nid: 0.0 for nid in nodes}
        for aid in anchor_ids:
            if aid in activation:
                activation[aid] = anchor_scores.get(aid, 0.5)

        # 2. Propagate for T iterations
        for _t in range(ITERATIONS):
            new_activation = {}
            for nid in nodes:
                # Self-retention
                external = (1 - DELTA) * activation[nid]

                # Incoming propagation
                propagated = 0.0
                # Check all edges pointing TO this node
                for source_id, targets in edges.items():
                    for target_id, weight in targets:
                        if target_id == nid:
                            fan = max(fan_out.get(source_id, 1), 1)
                            propagated += SPREAD * weight * activation[source_id] / fan

                new_activation[nid] = external + propagated

            # Lateral inhibition: top-K winners suppress others
            sorted_nodes = sorted(new_activation.items(), key=lambda x: x[1], reverse=True)
            winners = set(nid for nid, _ in sorted_nodes[:TOP_K_INHIBIT])

            for nid in new_activation:
                if nid not in winners and new_activation[nid] > 0:
                    new_activation[nid] *= (1 - BETA)

            # Fire: apply sigmoid
            activation = {
                nid: _sigmoid(val) for nid, val in new_activation.items()
            }

        # 3. Filter and return
        return {
            nid: round(val, 6)
            for nid, val in activation.items()
            if val > MIN_ACTIVATION
        }

    def _load_graph(self, project_id: int | None) -> dict:
        """Load the project subgraph. Cached per project_id."""
        if project_id in self._graph_cache:
            return self._graph_cache[project_id]

        # Fetch all active memory IDs for this project
        if project_id is not None:
            node_rows = self.db.execute(
                "SELECT id FROM memories WHERE project_id = %s AND is_active = true LIMIT %s",
                (project_id, MAX_GRAPH_NODES),
            )
        else:
            node_rows = self.db.execute(
                "SELECT id FROM memories WHERE is_active = true LIMIT %s",
                (MAX_GRAPH_NODES,),
            )

        nodes = {r["id"] for r in node_rows}
        if not nodes:
            graph = {"nodes": set(), "edges": {}, "fan_out": {}}
            self._graph_cache[project_id] = graph
            return graph

        # Fetch all edges between these nodes
        placeholders = ",".join(["%s"] * len(nodes))
        edge_rows = self.db.execute(
            f"""
            SELECT source_id, target_id, COALESCE(edge_weight, 1.0) as weight
            FROM memory_relations
            WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
            """,
            tuple(nodes) + tuple(nodes),
        )

        edges: dict[int, list[tuple[int, float]]] = {}
        fan_out: dict[int, int] = {}
        for r in edge_rows:
            src = r["source_id"]
            tgt = r["target_id"]
            w = float(r["weight"])
            edges.setdefault(src, []).append((tgt, w))
            fan_out[src] = fan_out.get(src, 0) + 1

        graph = {"nodes": nodes, "edges": edges, "fan_out": fan_out}
        self._graph_cache[project_id] = graph

        logger.info(
            "Loaded graph: %d nodes, %d edges (project_id=%s)",
            len(nodes), sum(len(v) for v in edges.values()), project_id,
        )
        return graph

    def invalidate_cache(self, project_id: int | None = None):
        """Clear cached graph for a project (or all)."""
        if project_id is None:
            self._graph_cache.clear()
        else:
            self._graph_cache.pop(project_id, None)

    @staticmethod
    def compute_pagerank(
        nodes: set[int],
        edges: dict[int, list[tuple[int, float]]],
        damping: float = 0.85,
        iterations: int = 20,
    ) -> dict[int, float]:
        """Compute PageRank for the graph.

        Returns mapping of node_id -> pagerank score.
        Called during clustering runs.
        """
        n = len(nodes)
        if n == 0:
            return {}

        pr = {nid: 1.0 / n for nid in nodes}

        for _ in range(iterations):
            new_pr = {}
            for nid in nodes:
                # Sum of contributions from nodes pointing to nid
                rank_sum = 0.0
                for src, targets in edges.items():
                    for tgt, _w in targets:
                        if tgt == nid:
                            out_degree = len(edges.get(src, []))
                            if out_degree > 0:
                                rank_sum += pr[src] / out_degree

                new_pr[nid] = (1 - damping) / n + damping * rank_sum

            pr = new_pr

        return {nid: round(v, 8) for nid, v in pr.items()}
