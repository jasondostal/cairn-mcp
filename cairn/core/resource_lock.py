"""Resource locking — file ownership and contention prevention (ca-156).

Prevents Split Keel at the system level by giving agents exclusive
ownership of file paths during active work. Before an agent modifies
a file, it acquires a lock. If another agent already holds it, the
request is rejected with details about the current owner.

Locks are scoped to a project and are automatically released when a
work item completes. Supports glob patterns (e.g., "src/api/*.py")
for broad ownership claims.

Uses in-memory storage with an optional database backing for
persistence across server restarts.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceLock:
    """A file-level lock held by an agent/work item."""

    path: str  # File path or glob pattern
    owner: str  # Agent name or assignee
    work_item_id: str  # Display ID (e.g., "ca-42")
    acquired_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "owner": self.owner,
            "work_item_id": self.work_item_id,
            "acquired_at": self.acquired_at,
        }


@dataclass
class LockConflict:
    """Details of a lock conflict."""

    requested_path: str
    held_by: ResourceLock

    def to_dict(self) -> dict:
        return {
            "requested_path": self.requested_path,
            "held_by": self.held_by.to_dict(),
        }


class ResourceLockManager:
    """Manages file-level resource locks for multi-agent coordination.

    Thread-safe for single-process use. For multi-process deployments,
    use database-backed locking.
    """

    def __init__(self) -> None:
        self._mu = threading.Lock()
        # project -> path -> lock
        self._locks: dict[str, dict[str, ResourceLock]] = {}

    def acquire(
        self,
        project: str,
        paths: list[str],
        owner: str,
        work_item_id: str,
    ) -> list[LockConflict]:
        """Attempt to acquire locks on one or more file paths.

        Returns a list of conflicts (empty = all acquired successfully).
        If any conflict is found, NO locks are acquired (atomic).
        """
        with self._mu:
            project_locks = self._locks.setdefault(project, {})
            conflicts: list[LockConflict] = []

            # Check for conflicts first
            for path in paths:
                conflict = self._check_conflict(project_locks, path, owner, work_item_id)
                if conflict:
                    conflicts.append(conflict)

            if conflicts:
                return conflicts

            # No conflicts — acquire all locks
            for path in paths:
                project_locks[path] = ResourceLock(
                    path=path,
                    owner=owner,
                    work_item_id=work_item_id,
                )

            logger.info(
                "Acquired %d lock(s) for %s on %s (project: %s)",
                len(paths), owner, work_item_id, project,
            )
            return []

    def release(
        self,
        project: str,
        *,
        paths: list[str] | None = None,
        work_item_id: str | None = None,
        owner: str | None = None,
    ) -> int:
        """Release locks by path, work item, or owner.

        At least one filter must be provided. Returns count of released locks.
        """
        if not paths and not work_item_id and not owner:
            raise ValueError("Must provide at least one of: paths, work_item_id, owner")

        with self._mu:
            project_locks = self._locks.get(project)
            if not project_locks:
                return 0

            to_remove: list[str] = []
            for locked_path, lock in project_locks.items():
                if paths and locked_path in paths:
                    to_remove.append(locked_path)
                elif work_item_id and lock.work_item_id == work_item_id:
                    to_remove.append(locked_path)
                elif owner and lock.owner == owner:
                    to_remove.append(locked_path)

            for path in to_remove:
                del project_locks[path]

            if to_remove:
                logger.info(
                    "Released %d lock(s) in project %s (filter: paths=%s, wi=%s, owner=%s)",
                    len(to_remove), project, paths, work_item_id, owner,
                )
            return len(to_remove)

    def check(self, project: str, paths: list[str], owner: str | None = None) -> list[LockConflict]:
        """Check for conflicts without acquiring locks.

        If owner is provided, locks held by that owner are not treated as conflicts.
        """
        with self._mu:
            project_locks = self._locks.get(project, {})
            conflicts: list[LockConflict] = []
            for path in paths:
                conflict = self._check_conflict(project_locks, path, owner, None)
                if conflict:
                    conflicts.append(conflict)
            return conflicts

    def list_locks(
        self,
        project: str,
        *,
        owner: str | None = None,
        work_item_id: str | None = None,
    ) -> list[ResourceLock]:
        """List all active locks, optionally filtered by owner or work item."""
        with self._mu:
            project_locks = self._locks.get(project, {})
            result: list[ResourceLock] = []
            for lock in project_locks.values():
                if owner and lock.owner != owner:
                    continue
                if work_item_id and lock.work_item_id != work_item_id:
                    continue
                result.append(lock)
            return sorted(result, key=lambda l: l.path)

    def _check_conflict(
        self,
        project_locks: dict[str, ResourceLock],
        path: str,
        owner: str | None,
        work_item_id: str | None,
    ) -> LockConflict | None:
        """Check if a path conflicts with any existing lock.

        A conflict exists when:
        - The exact path is already locked by a different owner/work item
        - An existing glob pattern lock covers the requested path
        - The requested path (if a glob) covers an existing locked path
        """
        for locked_path, lock in project_locks.items():
            # Same owner + same work item = no conflict (re-acquire is OK)
            if owner and lock.owner == owner and (
                work_item_id is None or lock.work_item_id == work_item_id
            ):
                continue

            # Exact match
            if path == locked_path:
                return LockConflict(requested_path=path, held_by=lock)

            # Existing lock pattern covers requested path
            if fnmatch.fnmatch(path, locked_path):
                return LockConflict(requested_path=path, held_by=lock)

            # Requested pattern covers existing locked path
            if fnmatch.fnmatch(locked_path, path):
                return LockConflict(requested_path=path, held_by=lock)

        return None


# Process-wide singleton — shared by server.py and tool modules.
lock_manager = ResourceLockManager()
