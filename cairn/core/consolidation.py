"""Memory consolidation. Reviews project memories for duplicates and recommends actions.

Includes two modes:
- dedup: Find semantically similar pairs and recommend merge/promote/inactivate.
- synthesize: Cluster related memories and create higher-order insight memories.

ConsolidationWorker runs the synthesize mode on a schedule as a background daemon.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from cairn.core.analytics import track_operation
from cairn.core.utils import extract_json, parse_vector
from cairn.embedding.interface import EmbeddingInterface
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import ConsolidationConfig, LLMCapabilities
    from cairn.core.clustering import ClusterEngine
    from cairn.core.event_bus import EventBus
    from cairn.core.memory import MemoryStore
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Similarity threshold for candidate pairs
SIMILARITY_THRESHOLD = 0.85


class ConsolidationEngine:
    """Review project memories for duplicates and recommend merges/promotions/inactivations."""

    def __init__(
        self, db: Database, embedding: EmbeddingInterface, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.llm = llm
        self.capabilities = capabilities

    @track_operation("consolidate")
    def consolidate(self, project: str, dry_run: bool = True) -> dict:
        """Analyze project memories and recommend/apply consolidation actions.

        Args:
            project: Project name to consolidate.
            dry_run: If True (default), only recommend. If False, apply changes.

        Returns:
            Dict with recommendations and optionally applied changes.
        """
        from cairn.llm.prompts import build_consolidation_messages

        can_consolidate = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.consolidation
        )

        if not can_consolidate:
            return {"error": "Consolidation requires LLM"}

        # Fetch all active memories for the project
        rows = self.db.execute(
            """
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.embedding, m.created_at
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE p.name = %s AND m.is_active = true
            ORDER BY m.created_at ASC
            """,
            (project,),
        )

        if len(rows) < 2:
            return {
                "project": project,
                "memory_count": len(rows),
                "candidates": [],
                "recommendations": [],
                "applied": False,
            }

        # Parse embeddings and compute pairwise similarity (skip memories without embeddings)
        filtered = [(r, parse_vector(r["embedding"])) for r in rows]
        filtered = [(r, v) for r, v in filtered if v is not None]
        if len(filtered) < 2:
            return {
                "project": project,
                "memory_count": len(rows),
                "candidates": [],
                "recommendations": [],
                "applied": False,
            }
        rows = [r for r, _ in filtered]
        ids = [r["id"] for r in rows]
        embeddings = [v for _, v in filtered]

        embeddings_matrix = np.array(embeddings)
        sim_matrix = cosine_similarity(embeddings_matrix)

        # Find pairs above threshold
        candidates = []
        seen = set()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if sim_matrix[i][j] >= SIMILARITY_THRESHOLD:
                    pair_key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
                    if pair_key not in seen:
                        seen.add(pair_key)
                        candidates.append({
                            "id_a": ids[i],
                            "id_b": ids[j],
                            "similarity": round(float(sim_matrix[i][j]), 4),
                            "summary_a": rows[i].get("summary") or rows[i]["content"][:200],
                            "summary_b": rows[j].get("summary") or rows[j]["content"][:200],
                        })

        if not candidates:
            return {
                "project": project,
                "memory_count": len(rows),
                "candidates": [],
                "recommendations": [],
                "applied": False,
            }

        # Ask LLM for recommendations
        try:
            assert self.llm is not None
            messages = build_consolidation_messages(candidates, project)
            raw = self.llm.generate(messages, max_tokens=1024)
            recommendations = extract_json(raw, json_type="array") or []
        except Exception:
            logger.warning("Consolidation LLM call failed", exc_info=True)
            return {
                "project": project,
                "memory_count": len(rows),
                "candidates": candidates,
                "recommendations": [],
                "applied": False,
                "error": "LLM call failed, showing candidates only",
            }

        result = {
            "project": project,
            "memory_count": len(rows),
            "candidates": candidates,
            "recommendations": recommendations,
            "applied": False,
        }

        # Apply if not dry_run
        if not dry_run and recommendations and isinstance(recommendations, list):
            applied_count = self._apply_recommendations(recommendations)
            result["applied"] = True
            result["applied_count"] = applied_count

        return result

    def _apply_recommendations(self, recommendations: list[dict]) -> int:
        """Apply consolidation recommendations. Returns count of applied actions."""
        applied = 0
        for rec in recommendations:
            action = rec.get("action")
            try:
                if action == "merge":
                    # Inactivate the secondary memory, keep the primary
                    secondary_id = rec.get("inactivate_id")
                    if secondary_id:
                        self.db.execute(
                            """
                            UPDATE memories
                            SET is_active = false, inactive_reason = %s, updated_at = NOW()
                            WHERE id = %s
                            """,
                            (f"Consolidated: {rec.get('reason', 'duplicate')}", secondary_id),
                        )
                        applied += 1

                elif action == "promote":
                    # Change memory_type to 'rule'
                    memory_id = rec.get("memory_id")
                    if memory_id:
                        self.db.execute(
                            "UPDATE memories SET memory_type = 'rule', updated_at = NOW() WHERE id = %s",
                            (memory_id,),
                        )
                        applied += 1

                elif action == "inactivate":
                    memory_id = rec.get("memory_id")
                    if memory_id:
                        self.db.execute(
                            """
                            UPDATE memories
                            SET is_active = false, inactive_reason = %s, updated_at = NOW()
                            WHERE id = %s
                            """,
                            (rec.get("reason", "Consolidation"), memory_id),
                        )
                        applied += 1

            except Exception:
                logger.warning("Failed to apply recommendation: %s", rec, exc_info=True)

        if applied:
            self.db.commit()
        return applied

    # ------------------------------------------------------------------
    # Synthesize mode — cluster → LLM → higher-order memory
    # ------------------------------------------------------------------

    @track_operation("consolidate.synthesize")
    def synthesize(self, project: str, *, dry_run: bool = True,
                   cluster_engine: ClusterEngine | None = None,
                   memory_store: MemoryStore | None = None,
                   event_bus: EventBus | None = None,
                   config: ConsolidationConfig | None = None) -> dict:
        """Synthesize higher-order memories from clusters.

        Finds dense clusters of related memories, asks LLM to create a
        single insight memory, then demotes the originals.

        Args:
            project: Project name.
            dry_run: If True, only preview. If False, create synthesis memories.
            cluster_engine: ClusterEngine for accessing clusters.
            memory_store: MemoryStore for creating new memories.
            event_bus: EventBus for publishing events.
            config: ConsolidationConfig with thresholds.
        """
        if not self.llm or not cluster_engine:
            return {"error": "Synthesize requires LLM and ClusterEngine"}

        min_size = config.min_cluster_size if config else 3
        sim_threshold = config.similarity_threshold if config else 0.80
        max_per_run = config.max_per_run if config else 10

        # Ensure clusters are fresh
        cluster_engine.run_clustering(project)

        clusters = cluster_engine.get_clusters(
            project=project, min_confidence=0.3, limit=50,
        )

        # Filter to eligible clusters
        eligible = []
        for c in clusters:
            if c["member_count"] < min_size:
                continue
            if len(c.get("member_ids", [])) < min_size:
                continue

            # Check mean pairwise similarity of members
            member_ids = c["member_ids"]
            rows = self.db.execute(
                f"""
                SELECT id, embedding FROM memories
                WHERE id IN ({','.join(['%s'] * len(member_ids))})
                  AND embedding IS NOT NULL AND is_active = true
                  AND consolidated_into IS NULL
                """,
                tuple(member_ids),
            )
            if len(rows) < min_size:
                continue

            vecs = [parse_vector(r["embedding"]) for r in rows]
            vecs = [v for v in vecs if v is not None]
            if len(vecs) < min_size:
                continue

            mat = np.array(vecs)
            sim_mat = cosine_similarity(mat)
            # Mean of upper triangle (excluding diagonal)
            n = len(vecs)
            if n < 2:
                continue
            upper = sim_mat[np.triu_indices(n, k=1)]
            mean_sim = float(np.mean(upper))

            if mean_sim >= sim_threshold:
                eligible.append({
                    "cluster_id": c["id"],
                    "label": c["label"],
                    "member_ids": [r["id"] for r in rows],
                    "member_count": len(rows),
                    "mean_similarity": round(mean_sim, 4),
                })

        eligible = eligible[:max_per_run]

        if not eligible:
            return {
                "project": project,
                "eligible_clusters": 0,
                "synthesized": 0,
                "dry_run": dry_run,
            }

        if dry_run:
            return {
                "project": project,
                "eligible_clusters": len(eligible),
                "candidates": eligible,
                "synthesized": 0,
                "dry_run": True,
            }

        # Live mode: synthesize each cluster
        synthesized = []
        for cluster in eligible:
            try:
                result = self._synthesize_cluster(
                    project, cluster, memory_store=memory_store,
                    event_bus=event_bus,
                )
                if result:
                    synthesized.append(result)
            except Exception:
                logger.warning(
                    "Failed to synthesize cluster %s", cluster["cluster_id"],
                    exc_info=True,
                )

        return {
            "project": project,
            "eligible_clusters": len(eligible),
            "synthesized": len(synthesized),
            "results": synthesized,
            "dry_run": False,
        }

    def _synthesize_cluster(
        self, project: str, cluster: dict, *,
        memory_store: MemoryStore | None = None,
        event_bus: EventBus | None = None,
    ) -> dict | None:
        """Synthesize a single cluster into one higher-order memory."""
        member_ids = cluster["member_ids"]

        # Fetch full content of members
        rows = self.db.execute(
            f"""
            SELECT id, content, summary, memory_type, importance, tags
            FROM memories
            WHERE id IN ({','.join(['%s'] * len(member_ids))})
            ORDER BY importance DESC, created_at DESC
            """,
            tuple(member_ids),
        )
        if not rows:
            return None

        # Build synthesis prompt
        member_texts = []
        for r in rows:
            text = r["summary"] or r["content"][:500]
            member_texts.append(f"  Memory #{r['id']} ({r['memory_type']}, importance={r['importance']}):\n    {text}")

        messages = [
            {"role": "system", "content": (
                "You are a knowledge consolidation engine. Given a cluster of related memories, "
                "synthesize them into a single higher-order insight. The insight should capture "
                "the pattern, principle, or learning that emerges from the individual memories. "
                "Be concise but complete. Write in a way that makes the originals unnecessary "
                "for understanding the key insight. Output ONLY the synthesized insight text."
            )},
            {"role": "user", "content": (
                f"Project: {project}\n"
                f"Cluster: {cluster['label']} ({cluster['member_count']} memories, "
                f"similarity={cluster['mean_similarity']})\n\n"
                f"Members:\n" + "\n".join(member_texts)
            )},
        ]

        try:
            assert self.llm is not None
            synthesis_text = self.llm.generate(messages, max_tokens=512)
        except Exception:
            logger.warning("LLM synthesis failed for cluster %s", cluster["cluster_id"], exc_info=True)
            return None

        if not synthesis_text or not synthesis_text.strip():
            return None

        # Create the parent memory
        if memory_store:
            result = memory_store.store(
                content=synthesis_text.strip(),
                project=project,
                memory_type="learning",
                importance=0.8,
                tags=["synthesized", "consolidation"],
                enrich=False,  # Don't re-extract, this is already distilled
            )
            parent_id = result.get("id")
        else:
            # Fallback: direct insert
            from cairn.core.utils import get_or_create_project
            project_id = get_or_create_project(self.db, project)
            row = self.db.execute_one(
                """
                INSERT INTO memories (project_id, content, memory_type, importance, tags)
                VALUES (%s, %s, 'learning', 0.8, %s)
                RETURNING id
                """,
                (project_id, synthesis_text.strip(), ["synthesized", "consolidation"]),
            )
            assert row is not None
            parent_id = row["id"]

        if not parent_id:
            return None

        # Demote originals: set consolidated_into and halve importance
        placeholders = ",".join(["%s"] * len(member_ids))
        self.db.execute(
            f"""
            UPDATE memories
            SET consolidated_into = %s,
                importance = GREATEST(0.1, importance * 0.5),
                updated_at = NOW()
            WHERE id IN ({placeholders})
            """,
            (parent_id, *member_ids),
        )

        # Link originals to parent via memory_relations
        for mid in member_ids:
            self.db.execute(
                """
                INSERT INTO memory_relations (source_id, target_id, relation)
                VALUES (%s, %s, 'extends')
                ON CONFLICT DO NOTHING
                """,
                (mid, parent_id),
            )

        self.db.commit()

        logger.info(
            "Synthesized cluster %s → memory #%d (%d originals demoted)",
            cluster["cluster_id"], parent_id, len(member_ids),
        )

        # Publish event
        if event_bus:
            try:
                event_bus.publish(
                    session_name="",
                    event_type="memory.consolidated",
                    project=project,
                    payload={
                        "parent_id": parent_id,
                        "original_ids": member_ids,
                        "cluster_id": cluster["cluster_id"],
                    },
                )
            except Exception:
                logger.warning("Failed to publish memory.consolidated", exc_info=True)

        return {
            "parent_id": parent_id,
            "original_ids": member_ids,
            "cluster_label": cluster["label"],
        }


class ConsolidationWorker:
    """Background daemon that runs cluster-based memory consolidation on a schedule.

    Mirrors the DecayWorker pattern: daemon thread, configurable interval,
    dry-run mode, exponential backoff on errors.
    """

    MAX_BACKOFF = 3600.0  # 1 hour max between retries

    def __init__(
        self,
        engine: ConsolidationEngine,
        db: Database,
        config: ConsolidationConfig,
        *,
        cluster_engine: ClusterEngine | None = None,
        memory_store: MemoryStore | None = None,
        event_bus: EventBus | None = None,
    ):
        self.engine = engine
        self.db = db
        self.config = config
        self.cluster_engine = cluster_engine
        self.memory_store = memory_store
        self.event_bus = event_bus
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.enabled:
            logger.info("ConsolidationWorker: disabled")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ConsolidationWorker",
        )
        self._thread.start()
        mode = "DRY RUN" if self.config.dry_run else "LIVE"
        logger.info(
            "ConsolidationWorker: started (%s, interval=%dh, min_cluster=%d, similarity=%.2f)",
            mode, self.config.interval_hours, self.config.min_cluster_size,
            self.config.similarity_threshold,
        )

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("ConsolidationWorker: thread did not stop within timeout")
        else:
            logger.info("ConsolidationWorker: stopped")
        self._thread = None

    def _run_loop(self) -> None:
        poll_interval = self.config.interval_hours * 3600.0
        while not self._stop_event.is_set():
            try:
                self._scan_all_projects()
                poll_interval = self.config.interval_hours * 3600.0
            except Exception:
                logger.warning("ConsolidationWorker: scan failed", exc_info=True)
                poll_interval = min(poll_interval * 2, self.MAX_BACKOFF)
            self._stop_event.wait(timeout=poll_interval)

    def _scan_all_projects(self) -> None:
        """Run consolidation across all projects."""
        rows = self.db.execute("SELECT name FROM projects")
        for row in rows:
            project = row["name"]
            try:
                result = self.engine.synthesize(
                    project,
                    dry_run=self.config.dry_run,
                    cluster_engine=self.cluster_engine,
                    memory_store=self.memory_store,
                    event_bus=self.event_bus,
                    config=self.config,
                )
                if result.get("synthesized", 0) > 0:
                    logger.info(
                        "ConsolidationWorker: synthesized %d clusters for %s",
                        result["synthesized"], project,
                    )
                elif result.get("eligible_clusters", 0) > 0 and self.config.dry_run:
                    logger.info(
                        "ConsolidationWorker [DRY RUN]: %d eligible clusters for %s",
                        result["eligible_clusters"], project,
                    )
            except Exception:
                logger.warning(
                    "ConsolidationWorker: failed for project %s",
                    project, exc_info=True,
                )
