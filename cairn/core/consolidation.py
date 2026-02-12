"""Memory consolidation. Reviews project memories for duplicates and recommends actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from cairn.core.analytics import track_operation
from cairn.core.utils import extract_json
from cairn.embedding.interface import EmbeddingInterface
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
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

        # Parse embeddings and compute pairwise similarity
        ids = [r["id"] for r in rows]
        embeddings = []
        for r in rows:
            vec_str = r["embedding"]
            if isinstance(vec_str, str):
                vec = [float(x) for x in vec_str.strip("[]").split(",")]
            else:
                vec = list(vec_str)
            embeddings.append(vec)

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
        if not dry_run and recommendations:
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
