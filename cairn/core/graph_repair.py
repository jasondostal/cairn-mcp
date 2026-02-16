"""Graph repair sweep for eventual-consistency dual-write.

Finds records with graph_synced=false and retries the graph write.
Run periodically or on demand to catch up after transient Neo4j failures.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.graph.interface import GraphProvider
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


def repair_unsynced(db: Database, graph: GraphProvider) -> dict:
    """Retry graph writes for all records where graph_synced=false.

    Returns counts of repaired records per table.
    """
    repaired = {"thinking_sequences": 0, "thoughts": 0, "tasks": 0}

    # --- Thinking sequences ---
    unsynced_seqs = db.execute(
        """SELECT ts.id, ts.project_id, ts.goal, ts.status
           FROM thinking_sequences ts
           WHERE ts.graph_synced = false""",
    )
    for seq in unsynced_seqs:
        try:
            graph_uuid = graph.create_thinking_sequence(
                pg_id=seq["id"],
                project_id=seq["project_id"],
                goal=seq["goal"],
                status=seq["status"],
            )
            db.execute(
                "UPDATE thinking_sequences SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, seq["id"]),
            )
            db.commit()
            if seq["status"] == "completed":
                graph.complete_thinking_sequence(graph_uuid)
            repaired["thinking_sequences"] += 1
        except Exception:
            logger.warning("Repair failed for thinking_sequence #%d", seq["id"], exc_info=True)

    # --- Thoughts ---
    unsynced_thoughts = db.execute(
        """SELECT t.id, t.sequence_id, t.thought_type, t.content,
                  ts.graph_uuid AS seq_graph_uuid
           FROM thoughts t
           JOIN thinking_sequences ts ON t.sequence_id = ts.id
           WHERE t.graph_synced = false AND ts.graph_uuid IS NOT NULL""",
    )
    for thought in unsynced_thoughts:
        try:
            graph_uuid = graph.create_thought(
                pg_id=thought["id"],
                sequence_uuid=thought["seq_graph_uuid"],
                thought_type=thought["thought_type"],
                content=thought["content"],
            )
            db.execute(
                "UPDATE thoughts SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, thought["id"]),
            )
            db.commit()
            repaired["thoughts"] += 1
        except Exception:
            logger.warning("Repair failed for thought #%d", thought["id"], exc_info=True)

    # --- Tasks ---
    unsynced_tasks = db.execute(
        "SELECT id, project_id, description, status FROM tasks WHERE graph_synced = false",
    )
    for task in unsynced_tasks:
        try:
            graph_uuid = graph.create_task(
                pg_id=task["id"],
                project_id=task["project_id"],
                description=task["description"],
                status=task["status"],
            )
            db.execute(
                "UPDATE tasks SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, task["id"]),
            )
            db.commit()
            if task["status"] == "completed":
                graph.complete_task(graph_uuid)
            repaired["tasks"] += 1
        except Exception:
            logger.warning("Repair failed for task #%d", task["id"], exc_info=True)

    total = sum(repaired.values())
    if total > 0:
        logger.info("Graph repair: %d records synced (%s)", total, repaired)
    return repaired
