"""Code-aware drift detection.

Compares file content hashes stored at memory creation time against
current hashes provided by the caller. Returns memories with stale
file references.

Pull-based: the caller provides current hashes because Cairn
runs on a different host than the codebase.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.utils import get_or_create_project

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detect memories with stale file references by hash comparison."""

    def __init__(self, db: Database):
        self.db = db

    @track_operation("drift_check")
    def check(
        self,
        project: str | None = None,
        files: list[dict] | None = None,
    ) -> dict:
        """Check for drift between stored and current file hashes.

        Args:
            project: Filter to a specific project. Omit to check all.
            files: List of {path: str, hash: str} — current file content hashes.

        Returns:
            Dict with checked_files, stale_memories, clean_count, stale_count.
        """
        if not files:
            return {
                "checked_files": 0,
                "stale_memories": [],
                "clean_count": 0,
                "stale_count": 0,
            }

        # Build a lookup: path -> current_hash
        current_hashes = {}
        for f in files:
            path = f.get("path")
            hash_val = f.get("hash")
            if path and hash_val:
                current_hashes[path] = hash_val

        if not current_hashes:
            return {
                "checked_files": 0,
                "stale_memories": [],
                "clean_count": 0,
                "stale_count": 0,
            }

        # Query memories that have file_hashes for any of the provided paths
        path_patterns = list(current_hashes.keys())
        where = ["m.is_active = true", "m.file_hashes != '{}'::jsonb"]
        params: list = []

        if project:
            where.append("p.name = %s")
            params.append(project)

        # Use jsonb ?| to check if any of the provided paths exist in file_hashes
        where.append("m.file_hashes ?| %s")
        params.append(path_patterns)

        where_clause = " AND ".join(where)

        rows = self.db.execute(
            f"""
            SELECT m.id, m.summary, m.memory_type, m.importance,
                   m.file_hashes, m.related_files,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )

        stale_memories = []
        clean_count = 0

        for row in rows:
            stored_hashes = row["file_hashes"] or {}
            if isinstance(stored_hashes, str):
                stored_hashes = json.loads(stored_hashes)

            changed_files = []
            for path, stored_hash in stored_hashes.items():
                if path in current_hashes and current_hashes[path] != stored_hash:
                    changed_files.append({
                        "path": path,
                        "stored_hash": stored_hash,
                        "current_hash": current_hashes[path],
                    })

            if changed_files:
                stale_memories.append({
                    "id": row["id"],
                    "summary": row["summary"] or f"Memory #{row['id']}",
                    "memory_type": row["memory_type"],
                    "importance": float(row["importance"]),
                    "project": row["project"],
                    "changed_files": changed_files,
                })
            else:
                clean_count += 1

        return {
            "checked_files": len(current_hashes),
            "stale_memories": stale_memories,
            "clean_count": clean_count,
            "stale_count": len(stale_memories),
        }
