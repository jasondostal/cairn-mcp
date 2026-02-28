"""Concurrent agent observability — live multi-agent dashboard (ca-159).

Aggregates multi-agent state into a single dashboard view:
- Active agents with their current work items and heartbeat status
- Resource lock state across all agents
- Progress summary for monitored epics
- Anti-pattern warnings

Designed for the cairn-ui dashboard and coordinator agents.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.resource_lock import ResourceLockManager

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class AgentDashboard:
    """Aggregates multi-agent state for observability."""

    def __init__(
        self,
        db: Database,
        lock_manager: ResourceLockManager | None = None,
    ) -> None:
        self.db = db
        self.lock_manager = lock_manager

    @track_operation("dashboard.active_agents")
    def active_agents(self, project: str | None = None) -> list[dict]:
        """List all agents with active (in_progress) work items.

        Returns agent name, current work items, heartbeat age, and state.
        """
        conditions = ["wi.assignee IS NOT NULL", "wi.status = 'in_progress'"]
        params: list = []

        if project:
            conditions.append("p.name = %s")
            params.append(project)

        where = " AND ".join(conditions)

        rows = self.db.execute(
            f"""
            SELECT wi.assignee,
                   wi.id, wi.seq_num, wi.title, wi.agent_state,
                   wi.last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - wi.last_heartbeat)) / 60.0
                       AS heartbeat_age_minutes,
                   p.name as project, p.work_item_prefix
            FROM work_items wi
            JOIN projects p ON wi.project_id = p.id
            WHERE {where}
            ORDER BY wi.assignee, wi.created_at
            """,
            tuple(params),
        )

        # Group by agent
        agents: dict[str, dict] = {}
        for r in rows:
            name = r["assignee"]
            if name not in agents:
                agents[name] = {
                    "agent_name": name,
                    "work_items": [],
                    "total_items": 0,
                }

            prefix = r.get("work_item_prefix") or "wi"
            display_id = f"{prefix}-{r['seq_num']}" if r.get("seq_num") else str(r["id"])

            heartbeat_age = round(r["heartbeat_age_minutes"], 1) if r["heartbeat_age_minutes"] else None

            agents[name]["work_items"].append({
                "id": r["id"],
                "display_id": display_id,
                "title": r["title"],
                "project": r["project"],
                "agent_state": r["agent_state"],
                "heartbeat_age_minutes": heartbeat_age,
                "stale": heartbeat_age is not None and heartbeat_age > 10,
            })
            agents[name]["total_items"] += 1

        return list(agents.values())

    @track_operation("dashboard.overview")
    def overview(self, project: str | None = None) -> dict:
        """Full dashboard overview — agents, locks, and summary stats."""
        agents = self.active_agents(project)

        # Lock summary
        locks_by_project: dict[str, int] = {}
        lock_conflicts: int = 0
        if self.lock_manager:
            # Gather locks from all projects mentioned in active work
            seen_projects: set[str] = set()
            for agent in agents:
                for wi in agent["work_items"]:
                    seen_projects.add(wi["project"])

            if project:
                seen_projects.add(project)

            for proj in seen_projects:
                proj_locks = self.lock_manager.list_locks(proj)
                if proj_locks:
                    locks_by_project[proj] = len(proj_locks)

        # Summary stats
        total_agents = len(agents)
        total_items = sum(a["total_items"] for a in agents)
        stale_count = sum(
            1 for a in agents
            for wi in a["work_items"]
            if wi.get("stale")
        )

        return {
            "total_active_agents": total_agents,
            "total_active_items": total_items,
            "stale_agents": stale_count,
            "agents": agents,
            "locks": locks_by_project,
            "health": "healthy" if stale_count == 0 else "degraded",
        }

    @track_operation("dashboard.agent_detail")
    def agent_detail(self, agent_name: str) -> dict:
        """Detailed view of a single agent's state."""
        rows = self.db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.status, wi.agent_state,
                   wi.last_heartbeat, wi.item_type, wi.risk_tier,
                   wi.gate_type, wi.gate_data,
                   EXTRACT(EPOCH FROM (NOW() - wi.last_heartbeat)) / 60.0
                       AS heartbeat_age_minutes,
                   p.name as project, p.work_item_prefix
            FROM work_items wi
            JOIN projects p ON wi.project_id = p.id
            WHERE wi.assignee = %s
              AND wi.status IN ('in_progress', 'blocked')
            ORDER BY wi.created_at
            """,
            (agent_name,),
        )

        items = []
        for r in rows:
            prefix = r.get("work_item_prefix") or "wi"
            display_id = f"{prefix}-{r['seq_num']}" if r.get("seq_num") else str(r["id"])
            heartbeat_age = round(r["heartbeat_age_minutes"], 1) if r["heartbeat_age_minutes"] else None

            items.append({
                "id": r["id"],
                "display_id": display_id,
                "title": r["title"],
                "project": r["project"],
                "status": r["status"],
                "item_type": r["item_type"],
                "risk_tier": r["risk_tier"],
                "agent_state": r["agent_state"],
                "heartbeat_age_minutes": heartbeat_age,
                "stale": heartbeat_age is not None and heartbeat_age > 10,
                "gated": r["gate_type"] is not None,
                "gate_type": r["gate_type"],
            })

        # Completed work history (last 10)
        history = self.db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.completed_at,
                   p.name as project, p.work_item_prefix
            FROM work_items wi
            JOIN projects p ON wi.project_id = p.id
            WHERE wi.assignee = %s AND wi.status = 'done'
            ORDER BY wi.completed_at DESC
            LIMIT 10
            """,
            (agent_name,),
        )

        completed = []
        for r in history:
            prefix = r.get("work_item_prefix") or "wi"
            display_id = f"{prefix}-{r['seq_num']}" if r.get("seq_num") else str(r["id"])
            completed.append({
                "display_id": display_id,
                "title": r["title"],
                "project": r["project"],
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            })

        return {
            "agent_name": agent_name,
            "active_items": items,
            "completed_items": completed,
            "total_active": len(items),
            "total_completed": len(completed),
        }
