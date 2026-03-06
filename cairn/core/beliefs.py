"""Belief store — durable epistemic state with confidence and provenance.

Beliefs are post-decisional knowledge: things an agent (or the organization)
has come to hold as true through experience. They have confidence scores,
domain tagging, evidence linking, and can be challenged or retracted.

Beliefs are the downstream of working memory — hypotheses that crystallized,
tensions that resolved, observations that solidified into conviction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.utils import get_or_create_project, get_project

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

VALID_PROVENANCES = {"crystallized", "propagated", "observed", "stated"}
VALID_STATUSES = {"active", "superseded", "retracted"}


class BeliefStore:
    """Manages durable beliefs with confidence, domain, and evidence tracking."""

    def __init__(self, db: Database, event_bus: EventBus | None = None) -> None:
        self.db = db
        self.event_bus = event_bus

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @track_operation("belief.crystallize")
    def crystallize(
        self,
        project: str,
        content: str,
        *,
        domain: str | None = None,
        confidence: float = 0.7,
        evidence_ids: list[int] | None = None,
        agent_name: str | None = None,
        provenance: str = "crystallized",
    ) -> dict:
        """Create a new belief.

        Args:
            project: Project name.
            content: The belief content.
            domain: Area of expertise (deployment, architecture, etc.).
            confidence: Initial confidence score (0.0-1.0).
            evidence_ids: Memory IDs supporting this belief.
            agent_name: Who holds this belief (None = organizational).
            provenance: How it was formed (crystallized, propagated, observed, stated).
        """
        if provenance not in VALID_PROVENANCES:
            return {"error": f"Invalid provenance '{provenance}'. Must be one of: {VALID_PROVENANCES}"}

        confidence = max(0.0, min(1.0, confidence))
        project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO beliefs
                (project_id, agent_name, content, domain, confidence,
                 evidence_ids, provenance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, agent_name, content, domain, confidence,
             evidence_ids or [], provenance),
        )
        assert row is not None
        self.db.commit()

        belief_id = row["id"]
        logger.info(
            "Crystallized belief #%d (confidence=%.2f, domain=%s, project=%s)",
            belief_id, confidence, domain, project,
        )

        self._publish("belief.crystallized", project_id,
                       belief_id=belief_id, domain=domain, confidence=confidence,
                       agent_name=agent_name)

        return {
            "id": belief_id,
            "project": project,
            "agent_name": agent_name,
            "content": content,
            "domain": domain,
            "confidence": confidence,
            "evidence_ids": evidence_ids or [],
            "provenance": provenance,
            "status": "active",
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("belief.list")
    def list_beliefs(
        self,
        project: str,
        *,
        agent_name: str | None = None,
        domain: str | None = None,
        status: str = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """List beliefs for a project."""
        project_id = get_project(self.db, project)
        if project_id is None:
            return {"items": [], "total": 0}

        conditions = ["b.project_id = %s"]
        params: list = [project_id]

        if status:
            conditions.append("b.status = %s")
            params.append(status)
        if agent_name:
            conditions.append("b.agent_name = %s")
            params.append(agent_name)
        if domain:
            conditions.append("b.domain = %s")
            params.append(domain)

        where = " AND ".join(conditions)

        count_row = self.db.execute_one(
            f"SELECT count(*) as cnt FROM beliefs b WHERE {where}",
            tuple(params),
        )
        total = count_row["cnt"] if count_row else 0

        rows = self.db.execute(
            f"""
            SELECT b.id, b.agent_name, b.content, b.domain, b.confidence,
                   b.evidence_ids, b.provenance, b.superseded_by, b.status,
                   b.created_at, b.updated_at,
                   p.name as project
            FROM beliefs b
            LEFT JOIN projects p ON b.project_id = p.id
            WHERE {where}
            ORDER BY b.confidence DESC, b.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params) + (limit, offset),
        )

        return {
            "items": [self._row_to_dict(r) for r in rows],
            "total": total,
        }

    @track_operation("belief.get")
    def get(self, belief_id: int) -> dict | None:
        """Get full detail for a belief."""
        row = self.db.execute_one(
            """
            SELECT b.id, b.agent_name, b.content, b.domain, b.confidence,
                   b.evidence_ids, b.provenance, b.superseded_by, b.status,
                   b.created_at, b.updated_at,
                   p.name as project
            FROM beliefs b
            LEFT JOIN projects p ON b.project_id = p.id
            WHERE b.id = %s
            """,
            (belief_id,),
        )
        if not row:
            return None
        return self._row_to_dict(row)

    @track_operation("belief.challenge")
    def challenge(
        self,
        belief_id: int,
        *,
        evidence_id: int | None = None,
        reason: str | None = None,
        confidence_delta: float = -0.1,
    ) -> dict:
        """Challenge a belief, lowering its confidence.

        Args:
            belief_id: Belief to challenge.
            evidence_id: Memory ID providing counter-evidence (appended to evidence_ids).
            reason: Why the belief is being challenged.
            confidence_delta: How much to adjust confidence (negative to lower).
        """
        current = self.db.execute_one(
            "SELECT id, confidence, evidence_ids, project_id, status FROM beliefs WHERE id = %s",
            (belief_id,),
        )
        if not current:
            return {"error": f"Belief {belief_id} not found"}
        if current["status"] != "active":
            return {"error": f"Belief {belief_id} is {current['status']}, not active"}

        new_confidence = max(0.0, min(1.0, float(current["confidence"]) + confidence_delta))

        # Append counter-evidence if provided
        evidence_update = ""
        params: list = [new_confidence]
        if evidence_id is not None:
            evidence_update = ", evidence_ids = evidence_ids || %s::integer[]"
            params.append([evidence_id])

        params.append(belief_id)

        self.db.execute(
            f"""
            UPDATE beliefs
            SET confidence = %s{evidence_update}, updated_at = NOW()
            WHERE id = %s
            """,
            tuple(params),
        )
        self.db.commit()

        logger.info(
            "Challenged belief #%d: confidence %.2f → %.2f (reason=%s)",
            belief_id, float(current["confidence"]), new_confidence, reason,
        )

        self._publish("belief.challenged", current["project_id"],
                       belief_id=belief_id, old_confidence=float(current["confidence"]),
                       new_confidence=new_confidence, reason=reason)

        return self.get(belief_id)

    @track_operation("belief.retract")
    def retract(self, belief_id: int, *, reason: str | None = None) -> dict:
        """Explicitly retract a belief — mark it as wrong."""
        row = self.db.execute_one(
            """
            UPDATE beliefs
            SET status = 'retracted', confidence = 0.0, updated_at = NOW()
            WHERE id = %s AND status = 'active'
            RETURNING id, project_id
            """,
            (belief_id,),
        )
        if not row:
            return {"error": f"Belief {belief_id} not found or not active"}
        self.db.commit()

        logger.info("Retracted belief #%d (reason=%s)", belief_id, reason)

        self._publish("belief.retracted", row["project_id"],
                       belief_id=belief_id, reason=reason)

        return self.get(belief_id)

    @track_operation("belief.supersede")
    def supersede(self, belief_id: int, new_belief_id: int) -> dict:
        """Mark a belief as superseded by a newer one."""
        row = self.db.execute_one(
            """
            UPDATE beliefs
            SET status = 'superseded', superseded_by = %s, updated_at = NOW()
            WHERE id = %s AND status = 'active'
            RETURNING id, project_id
            """,
            (new_belief_id, belief_id),
        )
        if not row:
            return {"error": f"Belief {belief_id} not found or not active"}
        self.db.commit()

        logger.info("Superseded belief #%d → #%d", belief_id, new_belief_id)

        self._publish("belief.superseded", row["project_id"],
                       belief_id=belief_id, new_belief_id=new_belief_id)

        return self.get(belief_id)

    # ------------------------------------------------------------------
    # Orient integration
    # ------------------------------------------------------------------

    def orient_beliefs(self, project: str, *, limit: int = 5) -> list[dict]:
        """Return top active beliefs for orient() injection."""
        project_id = get_project(self.db, project)
        if project_id is None:
            return []

        rows = self.db.execute(
            """
            SELECT id, content, domain, confidence, agent_name, provenance
            FROM beliefs
            WHERE project_id = %s AND status = 'active'
            ORDER BY confidence DESC, created_at DESC
            LIMIT %s
            """,
            (project_id, limit),
        )

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "domain": r["domain"],
                "confidence": round(float(r["confidence"]), 2),
                "agent_name": r["agent_name"],
                "provenance": r["provenance"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: dict) -> dict:
        result = {
            "id": row["id"],
            "project": row.get("project"),
            "agent_name": row.get("agent_name"),
            "content": row["content"],
            "domain": row.get("domain"),
            "confidence": round(float(row["confidence"]), 3),
            "evidence_ids": row.get("evidence_ids") or [],
            "provenance": row.get("provenance"),
            "superseded_by": row.get("superseded_by"),
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
        }
        return result

    def _publish(self, event_type: str, project_id: int | None = None, **payload) -> None:
        if not self.event_bus:
            return
        project_name = None
        if project_id:
            row = self.db.execute_one(
                "SELECT name FROM projects WHERE id = %s", (project_id,),
            )
            if row:
                project_name = row["name"]
        try:
            self.event_bus.publish(
                session_name="",
                event_type=event_type,
                project=project_name,
                payload=payload if payload else None,
            )
        except Exception:
            logger.warning("Failed to publish %s", event_type, exc_info=True)
