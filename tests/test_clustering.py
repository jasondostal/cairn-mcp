"""Test clustering engine: DBSCAN, centroids, confidence, staleness, degradation.

Tests use synthetic embeddings and mock DB/LLM — no real database or model calls.
The ClusterEngine's job is:
1. Detect staleness (time, growth, no prior run)
2. Run DBSCAN on cosine distance, compute centroids and confidence
3. Call LLM for labels/summaries (graceful fallback to generic)
4. Atomic write to DB
"""

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
from sklearn.metrics.pairwise import cosine_distances

from cairn.core.clustering import (
    ClusterEngine,
    DBSCAN_EPS,
    DBSCAN_MIN_SAMPLES,
    STALENESS_HOURS,
    STALENESS_GROWTH_RATIO,
)
from cairn.llm.interface import LLMInterface


# ============================================================
# Test Helpers
# ============================================================

class MockLLM(LLMInterface):
    """Returns a canned response for testing."""

    def __init__(self, response: str = ""):
        self._response = response

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        return self._response

    def get_model_name(self) -> str:
        return "mock"

    def get_context_size(self) -> int:
        return 4096


class ExplodingLLM(LLMInterface):
    """Always raises an exception."""

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        raise ConnectionError("LLM is down")

    def get_model_name(self) -> str:
        return "exploding"

    def get_context_size(self) -> int:
        return 0


def make_tight_cluster(center: np.ndarray, n: int = 5, noise: float = 0.02) -> np.ndarray:
    """Generate n embeddings tightly clustered around a center."""
    rng = np.random.RandomState(42)
    points = center + rng.randn(n, len(center)) * noise
    # Normalize to unit vectors (cosine similarity space)
    norms = np.linalg.norm(points, axis=1, keepdims=True)
    return points / norms


def make_mock_db_rows(ids: list[int], embeddings: np.ndarray) -> list[dict]:
    """Build fake DB rows matching what ClusterEngine expects."""
    rows = []
    for i, mid in enumerate(ids):
        rows.append({
            "id": mid,
            "embedding": "[" + ",".join(str(x) for x in embeddings[i]) + "]",
            "summary": f"Memory {mid} summary",
            "tags": ["test"],
            "auto_tags": ["auto"],
        })
    return rows


# ============================================================
# DBSCAN Finds Clusters
# ============================================================

def test_dbscan_finds_clusters():
    """Two well-separated clusters should be found by DBSCAN."""
    dim = 384
    rng = np.random.RandomState(0)

    # Two well-separated cluster centers
    center_a = rng.randn(dim)
    center_a /= np.linalg.norm(center_a)
    center_b = -center_a  # Opposite direction = maximum cosine distance

    cluster_a = make_tight_cluster(center_a, n=5, noise=0.02)
    cluster_b = make_tight_cluster(center_b, n=5, noise=0.02)

    all_embeddings = np.vstack([cluster_a, cluster_b])
    distance_matrix = cosine_distances(all_embeddings)

    from sklearn.cluster import DBSCAN
    dbscan = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="precomputed")
    labels = dbscan.fit_predict(distance_matrix)

    # Should find exactly 2 clusters, no noise
    unique_labels = set(labels)
    unique_labels.discard(-1)
    assert len(unique_labels) == 2, f"Expected 2 clusters, got {len(unique_labels)}"

    # First 5 should share a label, last 5 should share a different label
    assert len(set(labels[:5])) == 1
    assert len(set(labels[5:])) == 1
    assert labels[0] != labels[5]


# ============================================================
# Centroid Computation
# ============================================================

def test_centroid_computation():
    """Centroid should be the mean of member embeddings."""
    dim = 384
    rng = np.random.RandomState(1)
    center = rng.randn(dim)
    center /= np.linalg.norm(center)
    points = make_tight_cluster(center, n=5, noise=0.01)

    centroid = points.mean(axis=0)

    # Centroid should be very close to each point (within DBSCAN eps)
    for i in range(len(points)):
        dist = float(cosine_distances(points[i:i+1], centroid.reshape(1, -1))[0, 0])
        assert dist < 0.05, f"Point {i} too far from centroid: {dist}"


# ============================================================
# Confidence Scoring
# ============================================================

def test_confidence_tight_vs_loose():
    """Tight clusters should have higher confidence than loose clusters."""
    dim = 384
    rng = np.random.RandomState(2)
    center = rng.randn(dim)
    center /= np.linalg.norm(center)

    tight = make_tight_cluster(center, n=5, noise=0.01)
    loose = make_tight_cluster(center, n=5, noise=0.15)

    def compute_confidence(points):
        centroid = points.mean(axis=0)
        distances = np.array([
            float(cosine_distances(points[i:i+1], centroid.reshape(1, -1))[0, 0])
            for i in range(len(points))
        ])
        avg_dist = distances.mean()
        return max(0.0, min(1.0, 1.0 - (avg_dist / DBSCAN_EPS)))

    tight_conf = compute_confidence(tight)
    loose_conf = compute_confidence(loose)

    assert tight_conf > loose_conf, (
        f"Tight confidence ({tight_conf:.3f}) should exceed loose ({loose_conf:.3f})"
    )
    assert tight_conf > 0.5, f"Tight cluster confidence should be above 0.5: {tight_conf}"


# ============================================================
# Noise Handling
# ============================================================

def test_noise_not_stored():
    """DBSCAN noise points (label -1) should not appear in any cluster."""
    dim = 384
    rng = np.random.RandomState(3)

    # One cluster of 5 + 2 outliers far away
    center = rng.randn(dim)
    center /= np.linalg.norm(center)
    cluster = make_tight_cluster(center, n=5, noise=0.02)

    # Outliers: random directions far from center
    outlier1 = rng.randn(dim)
    outlier1 /= np.linalg.norm(outlier1)
    outlier2 = rng.randn(dim)
    outlier2 /= np.linalg.norm(outlier2)
    # Make sure outliers are far from center
    outlier1 = -center + rng.randn(dim) * 0.1
    outlier1 /= np.linalg.norm(outlier1)
    outlier2 = rng.randn(dim) * 2
    outlier2 /= np.linalg.norm(outlier2)

    all_embeddings = np.vstack([cluster, outlier1.reshape(1, -1), outlier2.reshape(1, -1)])
    distance_matrix = cosine_distances(all_embeddings)

    from sklearn.cluster import DBSCAN
    dbscan = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="precomputed")
    labels = dbscan.fit_predict(distance_matrix)

    # Noise points should be labeled -1
    noise_indices = [i for i, l in enumerate(labels) if l == -1]
    cluster_indices = [i for i, l in enumerate(labels) if l != -1]

    # The 5 cluster points should be in a cluster
    assert len(cluster_indices) >= 5
    # At least one outlier should be noise
    assert len(noise_indices) >= 1


# ============================================================
# Empty Project
# ============================================================

def test_empty_project():
    """Clustering an empty project should return gracefully."""
    db = MagicMock()
    embedding = MagicMock()

    # Project exists
    db.execute_one.side_effect = [
        {"id": 1},          # _resolve_project_id
        None,                # is_stale: no run exists
    ]
    db.execute.side_effect = [
        [],                  # run_clustering: no memories
    ]

    engine = ClusterEngine(db, embedding, llm=None)

    # is_stale returns True for no prior run
    db.execute_one.side_effect = [
        {"id": 1},          # _resolve_project_id
        None,                # is_stale: no run
    ]
    assert engine.is_stale("test-project") is True

    # run_clustering on empty project
    db.execute_one.side_effect = [
        {"id": 1},          # _resolve_project_id
    ]
    db.execute.side_effect = [
        [],                  # no memories
        [],                  # _record_run INSERT
    ]
    db.commit.return_value = None
    result = engine.run_clustering("test-project")

    assert result["cluster_count"] == 0
    assert result["noise_count"] == 0
    assert result["memory_count"] == 0


# ============================================================
# LLM Failure Fallback
# ============================================================

def test_llm_failure_produces_generic_labels():
    """When LLM fails, clusters should still form with generic labels."""
    engine = ClusterEngine(MagicMock(), MagicMock(), llm=ExplodingLLM())

    dim = 384
    rng = np.random.RandomState(4)
    center = rng.randn(dim)
    center /= np.linalg.norm(center)
    cluster = make_tight_cluster(center, n=5, noise=0.02)

    # Build fake cluster data
    cluster_data = [{
        "label_id": 0,
        "centroid": center.tolist(),
        "member_indices": list(range(5)),
        "member_ids": [1, 2, 3, 4, 5],
        "distances": [0.01] * 5,
        "avg_distance": 0.01,
        "confidence": 0.95,
    }]

    rows = make_mock_db_rows([1, 2, 3, 4, 5], cluster)

    summaries = engine._generate_summaries(cluster_data, rows)

    assert 0 in summaries
    assert "Cluster" in summaries[0]["label"]
    assert "5" in summaries[0]["summary"]  # mentions member count


def test_llm_success_produces_real_labels():
    """When LLM succeeds, we get real labels and summaries."""
    response = json.dumps([
        {"cluster_id": 0, "label": "Docker Setup", "summary": "Memories about Docker configuration."}
    ])
    engine = ClusterEngine(MagicMock(), MagicMock(), llm=MockLLM(response))

    cluster_data = [{
        "label_id": 0,
        "centroid": [0.0] * 384,
        "member_indices": [0, 1, 2],
        "member_ids": [1, 2, 3],
        "distances": [0.01] * 3,
        "avg_distance": 0.01,
        "confidence": 0.9,
    }]

    rows = [
        {"id": i, "embedding": "[" + ",".join(["0.0"] * 384) + "]",
         "summary": f"Memory {i}", "tags": ["docker"], "auto_tags": []}
        for i in [1, 2, 3]
    ]

    summaries = engine._generate_summaries(cluster_data, rows)

    assert summaries[0]["label"] == "Docker Setup"
    assert "Docker" in summaries[0]["summary"]


# ============================================================
# Staleness Detection
# ============================================================

def test_staleness_no_prior_run():
    """No prior run means always stale."""
    db = MagicMock()
    db.execute_one.return_value = None  # no run exists
    engine = ClusterEngine(db, MagicMock())

    assert engine.is_stale() is True


def test_staleness_time_trigger():
    """Run older than STALENESS_HOURS triggers reclustering."""
    db = MagicMock()
    old_time = datetime.now(timezone.utc) - timedelta(hours=STALENESS_HOURS + 1)

    db.execute_one.return_value = {"memory_count": 100, "created_at": old_time}
    engine = ClusterEngine(db, MagicMock())

    assert engine.is_stale() is True


def test_staleness_growth_trigger():
    """Memory growth exceeding STALENESS_GROWTH_RATIO triggers reclustering."""
    db = MagicMock()
    recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

    # First call: get last run (100 memories, recent)
    # Second call: count current memories (125 = 25% growth > 20% threshold)
    db.execute_one.side_effect = [
        {"memory_count": 100, "created_at": recent_time},  # last run
        {"count": 125},                                      # current count
    ]
    engine = ClusterEngine(db, MagicMock())

    assert engine.is_stale() is True


def test_staleness_not_stale():
    """Recent run with minimal growth should not be stale."""
    db = MagicMock()
    recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

    db.execute_one.side_effect = [
        {"memory_count": 100, "created_at": recent_time},  # last run
        {"count": 105},                                      # current count (5% growth)
    ]
    engine = ClusterEngine(db, MagicMock())

    assert engine.is_stale() is False


# ============================================================
# Vector Parsing
# ============================================================

def test_parse_vector():
    """pgvector string format should parse correctly."""
    engine = ClusterEngine(MagicMock(), MagicMock())

    vec = engine._parse_vector("[0.1,0.2,0.3]")
    assert vec == [0.1, 0.2, 0.3]

    vec = engine._parse_vector("[0.0]")
    assert vec == [0.0]
