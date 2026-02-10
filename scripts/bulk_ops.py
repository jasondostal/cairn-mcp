#!/usr/bin/env python3
"""Bulk memory operations: demote progress importance, move memories between projects.

Usage (inside container):
    python scripts/bulk_ops.py demote-progress [--importance 0.3] [--dry-run]
    python scripts/bulk_ops.py move-project --from <source> --to <target> [--dry-run]
    python scripts/bulk_ops.py cleanup-projects [--dry-run]

Reads CAIRN_* env vars for database connection.
"""

import argparse
import logging
import sys

from cairn.config import load_config
from cairn.storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bulk_ops")


def demote_progress(db: Database, target_importance: float, dry_run: bool):
    """Lower importance of all progress-type memories to target value."""
    rows = db.execute(
        """
        SELECT m.id, m.importance, p.name as project, m.summary
        FROM memories m
        LEFT JOIN projects p ON m.project_id = p.id
        WHERE m.memory_type = 'progress' AND m.is_active = true
          AND m.importance > %s
        ORDER BY m.importance DESC, m.id
        """,
        (target_importance,),
    )
    db.commit()

    if not rows:
        logger.info("No progress memories above %.2f — nothing to demote.", target_importance)
        return

    logger.info(
        "Found %d progress memories above %.2f importance.",
        len(rows), target_importance,
    )

    for r in rows[:5]:
        logger.info(
            "  Example: #%d (%.2f → %.2f) [%s] %s",
            r["id"], float(r["importance"]), target_importance,
            r["project"], (r["summary"] or "")[:80],
        )
    if len(rows) > 5:
        logger.info("  ... and %d more", len(rows) - 5)

    if dry_run:
        logger.info("DRY RUN — no changes made.")
        return

    db.execute(
        """
        UPDATE memories SET importance = %s, updated_at = NOW()
        WHERE memory_type = 'progress' AND is_active = true AND importance > %s
        """,
        (target_importance, target_importance),
    )
    db.commit()
    logger.info("Demoted %d progress memories to importance %.2f.", len(rows), target_importance)


def move_project(db: Database, source: str, target: str, dry_run: bool):
    """Move all memories from source project to target project."""
    # Get source project ID
    src = db.execute_one("SELECT id FROM projects WHERE name = %s", (source,))
    if not src:
        logger.error("Source project '%s' not found.", source)
        return

    # Get or create target project
    tgt = db.execute_one("SELECT id FROM projects WHERE name = %s", (target,))
    if not tgt:
        logger.info("Target project '%s' doesn't exist — will create.", target)
        if not dry_run:
            tgt = db.execute_one(
                "INSERT INTO projects (name) VALUES (%s) RETURNING id", (target,)
            )
    else:
        logger.info("Target project '%s' exists (id=%d).", target, tgt["id"])

    # Count memories to move
    count = db.execute_one(
        "SELECT COUNT(*) as n FROM memories WHERE project_id = %s AND is_active = true",
        (src["id"],),
    )
    total = count["n"]

    if total == 0:
        logger.info("No active memories in '%s' — nothing to move.", source)
        db.rollback()
        return

    # Show what would move
    samples = db.execute(
        """
        SELECT id, memory_type, importance, summary
        FROM memories WHERE project_id = %s AND is_active = true
        ORDER BY id LIMIT 5
        """,
        (src["id"],),
    )
    logger.info("Will move %d memories from '%s' → '%s':", total, source, target)
    for s in samples:
        logger.info(
            "  #%d [%s, %.2f] %s",
            s["id"], s["memory_type"], float(s["importance"]), (s["summary"] or "")[:80],
        )
    if total > 5:
        logger.info("  ... and %d more", total - 5)

    if dry_run:
        logger.info("DRY RUN — no changes made.")
        db.rollback()
        return

    # Move all data referencing the source project
    for table in [
        "memories",
        "project_documents",
        "tasks",
        "thinking_sequences",
        "session_events",
        "cairns",
    ]:
        db.execute(
            f"UPDATE {table} SET project_id = %s WHERE project_id = %s",
            (tgt["id"], src["id"]),
        )
    db.commit()
    logger.info("Moved %d memories + related data from '%s' → '%s'.", total, source, target)


def cleanup_projects(db: Database, dry_run: bool):
    """List empty/near-empty projects that are candidates for removal."""
    rows = db.execute(
        """
        SELECT p.id, p.name,
               COUNT(m.id) FILTER (WHERE m.is_active = true) as active,
               COUNT(m.id) FILTER (WHERE m.is_active = false) as inactive
        FROM projects p
        LEFT JOIN memories m ON m.project_id = p.id
        GROUP BY p.id, p.name
        ORDER BY active ASC, p.name
        """
    )
    db.commit()

    logger.info("Project inventory:")
    for r in rows:
        status = ""
        if r["active"] == 0 and r["inactive"] == 0:
            status = " ← EMPTY (safe to delete)"
        elif r["active"] == 0 and r["inactive"] > 0:
            status = " ← DEAD (only inactive memories)"
        logger.info(
            "  %-25s active=%-3d inactive=%-3d%s",
            r["name"], r["active"], r["inactive"], status,
        )


def main():
    parser = argparse.ArgumentParser(description="Bulk memory operations")
    sub = parser.add_subparsers(dest="command", required=True)

    # demote-progress
    dp = sub.add_parser("demote-progress", help="Lower importance of progress memories")
    dp.add_argument("--importance", type=float, default=0.3, help="Target importance (default: 0.3)")
    dp.add_argument("--dry-run", action="store_true", help="Preview without changes")

    # move-project
    mp = sub.add_parser("move-project", help="Move memories between projects")
    mp.add_argument("--from", dest="source", required=True, help="Source project name")
    mp.add_argument("--to", dest="target", required=True, help="Target project name")
    mp.add_argument("--dry-run", action="store_true", help="Preview without changes")

    # cleanup-projects
    cp = sub.add_parser("cleanup-projects", help="List empty/near-empty projects")
    cp.add_argument("--dry-run", action="store_true", help="(ignored, always read-only)")

    args = parser.parse_args()

    config = load_config()
    db = Database(config.db)
    db.connect()

    try:
        if args.command == "demote-progress":
            demote_progress(db, args.importance, args.dry_run)
        elif args.command == "move-project":
            move_project(db, args.source, args.target, args.dry_run)
        elif args.command == "cleanup-projects":
            cleanup_projects(db, args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()
