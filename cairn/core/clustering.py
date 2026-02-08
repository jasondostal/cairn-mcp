"""Clustering engine. DBSCAN on memory embeddings, LLM-generated summaries, lazy reclustering."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.manifold import TSNE
from sklearn.metrics.pairwise import cosine_distances

from cairn.core.utils import extract_json
from cairn.embedding.engine import EmbeddingEngine
from cairn.llm.prompts import build_cluster_summary_messages
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# DBSCAN parameters
# MiniLM-L6-v2 cosine distances for topically similar short texts: 0.4-0.8
# Cross-topic distances: 0.7-1.0. eps=0.65 captures coherent clusters.
DBSCAN_EPS = 0.65
DBSCAN_MIN_SAMPLES = 3

# Staleness thresholds
STALENESS_HOURS = 24
STALENESS_GROWTH_RATIO = 0.20  # 20% memory growth triggers recluster


class ClusterEngine:
    """DBSCAN clustering with LLM-generated summaries and lazy reclustering."""

    def __init__(self, db: Database, embedding: EmbeddingEngine, llm: LLMInterface | None = None):
        self.db = db
        self.embedding = embedding
        self.llm = llm

    # ============================================================
    # Staleness Detection
    # ============================================================

    def is_stale(self, project: str | None = None) -> bool:
        """Check if clustering needs to run for a project (or globally)."""
        project_id = self._resolve_project_id(project) if project else None

        # Get last clustering run
        if project_id:
            run = self.db.execute_one(
                "SELECT memory_count, created_at FROM clustering_runs "
                "WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            )
        else:
            run = self.db.execute_one(
                "SELECT memory_count, created_at FROM clustering_runs "
                "WHERE project_id IS NULL ORDER BY created_at DESC LIMIT 1",
            )

        # No run exists -> stale
        if not run:
            return True

        # Check time staleness
        now = datetime.now(timezone.utc)
        age_hours = (now - run["created_at"]).total_seconds() / 3600
        if age_hours > STALENESS_HOURS:
            return True

        # Check growth staleness
        current_count = self._count_active_memories(project_id)
        last_count = run["memory_count"]
        if last_count > 0 and (current_count - last_count) / last_count > STALENESS_GROWTH_RATIO:
            return True

        return False

    # ============================================================
    # Core Clustering
    # ============================================================

    def run_clustering(self, project: str | None = None) -> dict:
        """Run DBSCAN clustering for a project (or globally).

        Returns dict with cluster_count, noise_count, memory_count, duration_ms.
        """
        start = time.monotonic()
        project_id = self._resolve_project_id(project) if project else None

        # Fetch all active memory embeddings
        if project_id:
            rows = self.db.execute(
                "SELECT id, embedding::text, summary, tags, auto_tags FROM memories "
                "WHERE project_id = %s AND is_active = true AND embedding IS NOT NULL",
                (project_id,),
            )
        else:
            rows = self.db.execute(
                "SELECT id, embedding::text, summary, tags, auto_tags FROM memories "
                "WHERE is_active = true AND embedding IS NOT NULL",
            )

        memory_count = len(rows)

        # Not enough memories to cluster
        if memory_count < DBSCAN_MIN_SAMPLES:
            self._record_run(project_id, memory_count, 0, 0, start)
            return {"cluster_count": 0, "noise_count": 0, "memory_count": memory_count,
                    "duration_ms": self._elapsed_ms(start)}

        # Parse embeddings into numpy array
        memory_ids = [r["id"] for r in rows]
        embeddings = np.array([self._parse_vector(r["embedding"]) for r in rows])

        # DBSCAN on cosine distance
        distance_matrix = cosine_distances(embeddings)
        dbscan = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="precomputed")
        labels = dbscan.fit_predict(distance_matrix)

        # Group memories by cluster label (skip noise = -1)
        cluster_groups: dict[int, list[int]] = {}  # label -> list of row indices
        noise_count = 0
        for idx, label in enumerate(labels):
            if label == -1:
                noise_count += 1
                continue
            cluster_groups.setdefault(label, []).append(idx)

        # Compute centroids and confidence for each cluster
        cluster_data = []
        for label, member_indices in cluster_groups.items():
            member_vecs = embeddings[member_indices]
            centroid = member_vecs.mean(axis=0)

            # Distances from centroid
            distances = np.array([
                float(cosine_distances(member_vecs[i:i+1], centroid.reshape(1, -1))[0, 0])
                for i in range(len(member_indices))
            ])
            avg_distance = float(distances.mean())
            # Confidence: inverse of avg distance, normalized. Max cosine distance = 2.0
            confidence = max(0.0, min(1.0, 1.0 - (avg_distance / DBSCAN_EPS)))

            cluster_data.append({
                "label_id": label,
                "centroid": centroid.tolist(),
                "member_indices": member_indices,
                "member_ids": [memory_ids[i] for i in member_indices],
                "distances": distances.tolist(),
                "avg_distance": avg_distance,
                "confidence": confidence,
            })

        # Get LLM summaries (skip if no clusters formed)
        summaries = self._generate_summaries(cluster_data, rows) if cluster_data else {}

        # Atomic DB write: delete old, insert new
        self._write_clusters(project_id, cluster_data, summaries)
        self._record_run(project_id, memory_count, len(cluster_data), noise_count, start)

        duration_ms = self._elapsed_ms(start)
        logger.info(
            "Clustering complete: %d clusters, %d noise, %d memories, %dms",
            len(cluster_data), noise_count, memory_count, duration_ms,
        )

        return {
            "cluster_count": len(cluster_data),
            "noise_count": noise_count,
            "memory_count": memory_count,
            "duration_ms": duration_ms,
        }

    # ============================================================
    # Retrieval
    # ============================================================

    def get_clusters(
        self,
        project: str | None = None,
        topic: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[dict]:
        """Get clusters, optionally filtered by topic similarity and confidence."""
        project_id = self._resolve_project_id(project) if project else None

        # Fetch clusters
        if project_id:
            clusters = self.db.execute(
                "SELECT id, label, summary, centroid::text, member_count, "
                "avg_distance, confidence, created_at "
                "FROM clusters WHERE project_id = %s AND confidence >= %s "
                "ORDER BY member_count DESC",
                (project_id, min_confidence),
            )
        else:
            clusters = self.db.execute(
                "SELECT id, label, summary, centroid::text, member_count, "
                "avg_distance, confidence, created_at "
                "FROM clusters WHERE confidence >= %s "
                "ORDER BY member_count DESC",
                (min_confidence,),
            )

        if not clusters:
            return []

        # Topic filtering: embed topic, rank by cosine similarity to centroids
        if topic:
            topic_vec = np.array(self.embedding.embed(topic)).reshape(1, -1)
            scored = []
            for c in clusters:
                centroid = np.array(self._parse_vector(c["centroid"])).reshape(1, -1)
                similarity = 1.0 - float(cosine_distances(topic_vec, centroid)[0, 0])
                scored.append((similarity, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            clusters = [c for _, c in scored[:limit]]
        else:
            clusters = clusters[:limit]

        # Enrich with member IDs and sample memories
        result = []
        for c in clusters:
            members = self.db.execute(
                "SELECT cm.memory_id, cm.distance, m.summary "
                "FROM cluster_members cm "
                "JOIN memories m ON cm.memory_id = m.id "
                "WHERE cm.cluster_id = %s ORDER BY cm.distance",
                (c["id"],),
            )
            result.append({
                "id": c["id"],
                "label": c["label"],
                "summary": c["summary"],
                "member_count": c["member_count"],
                "confidence": c["confidence"],
                "created_at": c["created_at"].isoformat(),
                "member_ids": [m["memory_id"] for m in members],
                "sample_memories": [
                    {"id": m["memory_id"], "summary": m["summary"], "distance": m["distance"]}
                    for m in members[:5]
                ],
            })

        return result

    # ============================================================
    # Visualization
    # ============================================================

    def get_visualization(self, project: str | None = None) -> dict:
        """Run t-SNE on memory embeddings to produce 2D coordinates for visualization.

        Returns dict with 'points' list and 'generated_at' timestamp.
        """
        project_id = self._resolve_project_id(project) if project else None

        # Fetch active memories with embeddings
        if project_id:
            rows = self.db.execute(
                "SELECT m.id, m.embedding::text, m.summary, m.memory_type "
                "FROM memories m "
                "WHERE m.project_id = %s AND m.is_active = true AND m.embedding IS NOT NULL",
                (project_id,),
            )
        else:
            rows = self.db.execute(
                "SELECT m.id, m.embedding::text, m.summary, m.memory_type "
                "FROM memories m "
                "WHERE m.is_active = true AND m.embedding IS NOT NULL",
            )

        if not rows:
            return {"points": [], "generated_at": datetime.now(timezone.utc).isoformat()}

        memory_ids = [r["id"] for r in rows]
        embeddings = np.array([self._parse_vector(r["embedding"]) for r in rows])

        # t-SNE needs at least 2 samples; perplexity must be < n_samples
        n = len(embeddings)
        if n < 2:
            return {"points": [], "generated_at": datetime.now(timezone.utc).isoformat()}

        perplexity = min(30, max(2, n - 1))
        tsne = TSNE(n_components=2, perplexity=perplexity, random_state=42, metric="cosine")
        coords = tsne.fit_transform(embeddings)

        # Get cluster assignments for coloring
        cluster_map: dict[int, tuple[int, str]] = {}  # memory_id -> (cluster_id, label)
        members = self.db.execute(
            "SELECT cm.memory_id, cm.cluster_id, c.label "
            "FROM cluster_members cm "
            "JOIN clusters c ON c.id = cm.cluster_id",
        )
        for m in members:
            cluster_map[m["memory_id"]] = (m["cluster_id"], m["label"])

        points = []
        for i, row in enumerate(rows):
            mid = memory_ids[i]
            cinfo = cluster_map.get(mid)
            points.append({
                "id": mid,
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "summary": row["summary"],
                "memory_type": row["memory_type"],
                "cluster_id": cinfo[0] if cinfo else None,
                "cluster_label": cinfo[1] if cinfo else None,
            })

        return {
            "points": points,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ============================================================
    # Internals
    # ============================================================

    def _resolve_project_id(self, project_name: str) -> int | None:
        """Resolve project name to ID. Returns None if not found."""
        row = self.db.execute_one(
            "SELECT id FROM projects WHERE name = %s", (project_name,)
        )
        return row["id"] if row else None

    def _count_active_memories(self, project_id: int | None) -> int:
        """Count active memories for a project (or globally)."""
        if project_id:
            row = self.db.execute_one(
                "SELECT COUNT(*) as count FROM memories "
                "WHERE project_id = %s AND is_active = true",
                (project_id,),
            )
        else:
            row = self.db.execute_one(
                "SELECT COUNT(*) as count FROM memories WHERE is_active = true",
            )
        return row["count"] if row else 0

    def _parse_vector(self, text: str) -> list[float]:
        """Parse a pgvector string like '[0.1,0.2,...]' into a list of floats."""
        return [float(x) for x in text.strip("[]").split(",")]

    def _elapsed_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _generate_summaries(self, cluster_data: list[dict], rows: list[dict]) -> dict[int, dict]:
        """Call LLM to generate labels and summaries for clusters.

        Returns mapping of label_id -> {"label": ..., "summary": ...}.
        Falls back to generic labels on any failure.
        """
        if not self.llm:
            return self._generic_summaries(cluster_data)

        # Build input for prompt: cluster_id -> list of member summary strings
        prompt_clusters: dict[int, list[str]] = {}
        for cd in cluster_data:
            members = []
            for idx in cd["member_indices"]:
                r = rows[idx]
                summary = r["summary"] or "(no summary)"
                tags = (r["tags"] or []) + (r["auto_tags"] or [])
                tag_str = ", ".join(tags[:5]) if tags else "no tags"
                members.append(f"{summary} [{tag_str}]")
            prompt_clusters[cd["label_id"]] = members

        try:
            messages = build_cluster_summary_messages(prompt_clusters)
            raw = self.llm.generate(messages, max_tokens=1024)
            return self._parse_summaries(raw, cluster_data)
        except Exception:
            logger.warning("Cluster summary LLM call failed, using generic labels", exc_info=True)
            return self._generic_summaries(cluster_data)

    def _parse_summaries(self, raw: str, cluster_data: list[dict]) -> dict[int, dict]:
        """Parse LLM response into summary mapping. Falls back to generic on parse failure."""
        items = extract_json(raw, json_type="array")
        if items is None:
            logger.warning("No valid JSON array in cluster summary response")
            return self._generic_summaries(cluster_data)

        result = {}
        for item in items:
            cid = item.get("cluster_id")
            if cid is not None:
                result[cid] = {
                    "label": str(item.get("label", "Unlabeled"))[:255],
                    "summary": str(item.get("summary", "")),
                }
        return result

    def _generic_summaries(self, cluster_data: list[dict]) -> dict[int, dict]:
        """Generate generic labels when LLM is unavailable."""
        return {
            cd["label_id"]: {
                "label": f"Cluster {cd['label_id'] + 1}",
                "summary": f"Group of {len(cd['member_ids'])} semantically similar memories.",
            }
            for cd in cluster_data
        }

    def _write_clusters(self, project_id: int | None, cluster_data: list[dict],
                        summaries: dict[int, dict]) -> None:
        """Atomic write: delete old clusters for project, insert new ones."""
        # Delete old clusters
        if project_id:
            self.db.execute("DELETE FROM clusters WHERE project_id = %s", (project_id,))
        else:
            self.db.execute("DELETE FROM clusters WHERE project_id IS NULL")

        # Insert new clusters and members
        for cd in cluster_data:
            s = summaries.get(cd["label_id"], {"label": "Unlabeled", "summary": ""})

            row = self.db.execute_one(
                """
                INSERT INTO clusters (project_id, label, summary, centroid, member_count,
                                      avg_distance, confidence)
                VALUES (%s, %s, %s, %s::vector, %s, %s, %s)
                RETURNING id
                """,
                (
                    project_id,
                    s["label"],
                    s["summary"],
                    str(cd["centroid"]),
                    len(cd["member_ids"]),
                    cd["avg_distance"],
                    cd["confidence"],
                ),
            )
            cluster_id = row["id"]

            # Insert members
            for i, memory_id in enumerate(cd["member_ids"]):
                self.db.execute(
                    "INSERT INTO cluster_members (cluster_id, memory_id, distance) "
                    "VALUES (%s, %s, %s)",
                    (cluster_id, memory_id, cd["distances"][i]),
                )

        self.db.commit()

    def _record_run(self, project_id: int | None, memory_count: int,
                    cluster_count: int, noise_count: int, start: float) -> None:
        """Record a clustering run for staleness tracking."""
        self.db.execute(
            """
            INSERT INTO clustering_runs (project_id, memory_count, cluster_count,
                                         noise_count, duration_ms)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, memory_count, cluster_count, noise_count, self._elapsed_ms(start)),
        )
        self.db.commit()
