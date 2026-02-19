"""Startup reconciliation — PG wins over Neo4j.

On server start (after graph connects), compare PG state against Neo4j and
fix any mismatches.  Uses idempotent ensure_* methods so this is safe to
run repeatedly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.graph.interface import GraphProvider
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


def reconcile_graph(db: Database, graph: GraphProvider) -> dict:
    """Full reconciliation pass: work items, tasks, thinking sequences.

    PG is the source of truth — Neo4j is updated to match.
    Returns aggregate stats.
    """
    stats = {
        "work_items": _reconcile_work_items(db, graph),
        "tasks": _reconcile_tasks(db, graph),
        "thinking": _reconcile_thinking(db, graph),
    }
    total_fixed = sum(s.get("fixed", 0) for s in stats.values())
    total_backfilled = sum(s.get("backfilled", 0) for s in stats.values())
    if total_fixed or total_backfilled:
        logger.info(
            "Reconciliation complete: fixed=%d, backfilled=%d",
            total_fixed, total_backfilled,
        )
    else:
        logger.info("Reconciliation complete: no mismatches found")
    return stats


def _reconcile_work_items(db: Database, graph: GraphProvider) -> dict:
    """Reconcile all work items that are active or exist in Neo4j (PG wins)."""
    stats = {"checked": 0, "fixed": 0, "backfilled": 0}

    rows = db.execute(
        """
        SELECT id, project_id, title, description, item_type, priority,
               status, short_id, risk_tier, gate_type, assignee,
               completed_at, graph_uuid
        FROM work_items
        WHERE status NOT IN ('done', 'cancelled')
           OR graph_uuid IS NOT NULL
        """,
    )

    for row in rows:
        stats["checked"] += 1
        try:
            graph_uuid = graph.ensure_work_item(
                pg_id=row["id"],
                project_id=row["project_id"],
                title=row["title"],
                description=row.get("description") or "",
                item_type=row["item_type"],
                priority=row["priority"],
                status=row["status"],
                short_id=row["short_id"],
                risk_tier=row.get("risk_tier", 0),
                gate_type=row.get("gate_type"),
                assignee=row.get("assignee"),
                completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            )
            if not row.get("graph_uuid"):
                db.execute(
                    "UPDATE work_items SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                    (graph_uuid, row["id"]),
                )
                db.commit()
                stats["backfilled"] += 1
            stats["fixed"] += 1
        except Exception:
            logger.debug("Reconciliation: failed for work_item #%d", row["id"], exc_info=True)

    return stats


def _reconcile_tasks(db: Database, graph: GraphProvider) -> dict:
    """Reconcile pending tasks (PG wins)."""
    stats = {"checked": 0, "fixed": 0, "backfilled": 0}

    rows = db.execute(
        "SELECT id, project_id, description, status, completed_at, graph_uuid FROM tasks WHERE status = 'pending'",
    )

    for row in rows:
        stats["checked"] += 1
        try:
            graph_uuid = graph.ensure_task(
                pg_id=row["id"],
                project_id=row["project_id"],
                description=row.get("description") or "",
                status=row["status"],
                completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            )
            if not row.get("graph_uuid"):
                db.execute(
                    "UPDATE tasks SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                    (graph_uuid, row["id"]),
                )
                db.commit()
                stats["backfilled"] += 1
            stats["fixed"] += 1
        except Exception:
            logger.debug("Reconciliation: failed for task #%d", row["id"], exc_info=True)

    return stats


def _reconcile_thinking(db: Database, graph: GraphProvider) -> dict:
    """Reconcile active thinking sequences (PG wins)."""
    stats = {"checked": 0, "fixed": 0, "backfilled": 0}

    rows = db.execute(
        "SELECT id, project_id, goal, status, completed_at, graph_uuid FROM thinking_sequences WHERE status = 'active'",
    )

    for row in rows:
        stats["checked"] += 1
        try:
            graph_uuid = graph.ensure_thinking_sequence(
                pg_id=row["id"],
                project_id=row["project_id"],
                goal=row.get("goal") or "",
                status=row["status"],
                completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            )
            if not row.get("graph_uuid"):
                db.execute(
                    "UPDATE thinking_sequences SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                    (graph_uuid, row["id"]),
                )
                db.commit()
                stats["backfilled"] += 1
            stats["fixed"] += 1
        except Exception:
            logger.debug("Reconciliation: failed for thinking_sequence #%d", row["id"], exc_info=True)

    return stats
