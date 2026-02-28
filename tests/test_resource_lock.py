"""Tests for resource locking — file ownership and contention prevention (ca-156)."""

from __future__ import annotations

import pytest

from cairn.core.resource_lock import (
    LockConflict,
    ResourceLock,
    ResourceLockManager,
)


class TestResourceLock:
    """Test ResourceLock dataclass."""

    def test_creation(self):
        lock = ResourceLock(path="src/api.py", owner="agent-1", work_item_id="ca-42")
        assert lock.path == "src/api.py"
        assert lock.owner == "agent-1"
        assert lock.work_item_id == "ca-42"
        assert lock.acquired_at > 0

    def test_to_dict(self):
        lock = ResourceLock(path="src/api.py", owner="agent-1", work_item_id="ca-42")
        d = lock.to_dict()
        assert d["path"] == "src/api.py"
        assert d["owner"] == "agent-1"
        assert d["work_item_id"] == "ca-42"
        assert "acquired_at" in d


class TestLockConflict:
    """Test LockConflict dataclass."""

    def test_to_dict(self):
        lock = ResourceLock(path="src/api.py", owner="agent-1", work_item_id="ca-42")
        conflict = LockConflict(requested_path="src/api.py", held_by=lock)
        d = conflict.to_dict()
        assert d["requested_path"] == "src/api.py"
        assert d["held_by"]["owner"] == "agent-1"


class TestResourceLockManager:
    """Test ResourceLockManager operations."""

    def test_acquire_single_path(self):
        mgr = ResourceLockManager()
        conflicts = mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        assert conflicts == []

    def test_acquire_multiple_paths(self):
        mgr = ResourceLockManager()
        conflicts = mgr.acquire("proj", ["a.py", "b.py", "c.py"], "agent-1", "ca-42")
        assert conflicts == []
        locks = mgr.list_locks("proj")
        assert len(locks) == 3

    def test_acquire_conflict_exact_path(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/api.py"], "agent-2", "ca-43")
        assert len(conflicts) == 1
        assert conflicts[0].requested_path == "src/api.py"
        assert conflicts[0].held_by.owner == "agent-1"

    def test_acquire_atomic_on_conflict(self):
        """If any path conflicts, NO locks are acquired."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/new.py", "src/api.py"], "agent-2", "ca-43")
        assert len(conflicts) == 1
        # src/new.py should NOT have been acquired
        locks = mgr.list_locks("proj")
        assert len(locks) == 1  # Only the original lock

    def test_reacquire_same_owner_same_work_item(self):
        """Same owner + same work item can re-acquire (idempotent)."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        assert conflicts == []

    def test_different_work_item_same_owner_conflicts(self):
        """Same owner but different work item is a conflict."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-99")
        assert len(conflicts) == 1

    def test_different_projects_no_conflict(self):
        """Locks are scoped to projects."""
        mgr = ResourceLockManager()
        mgr.acquire("proj-a", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj-b", ["src/api.py"], "agent-2", "ca-43")
        assert conflicts == []

    def test_glob_pattern_lock_covers_specific_path(self):
        """A glob pattern lock blocks specific paths matching it."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/*.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/api.py"], "agent-2", "ca-43")
        assert len(conflicts) == 1

    def test_specific_path_blocks_matching_glob(self):
        """A specific locked path blocks a glob that covers it."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["src/api.py"], "agent-1", "ca-42")
        conflicts = mgr.acquire("proj", ["src/*.py"], "agent-2", "ca-43")
        assert len(conflicts) == 1


class TestRelease:
    """Test lock release operations."""

    def test_release_by_paths(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py", "b.py"], "agent-1", "ca-42")
        released = mgr.release("proj", paths=["a.py"])
        assert released == 1
        locks = mgr.list_locks("proj")
        assert len(locks) == 1
        assert locks[0].path == "b.py"

    def test_release_by_work_item_id(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py", "b.py"], "agent-1", "ca-42")
        mgr.acquire("proj", ["c.py"], "agent-2", "ca-43")
        released = mgr.release("proj", work_item_id="ca-42")
        assert released == 2
        locks = mgr.list_locks("proj")
        assert len(locks) == 1
        assert locks[0].work_item_id == "ca-43"

    def test_release_by_owner(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py"], "agent-1", "ca-42")
        mgr.acquire("proj", ["b.py"], "agent-1", "ca-43")
        mgr.acquire("proj", ["c.py"], "agent-2", "ca-44")
        released = mgr.release("proj", owner="agent-1")
        assert released == 2
        locks = mgr.list_locks("proj")
        assert len(locks) == 1
        assert locks[0].owner == "agent-2"

    def test_release_no_filter_raises(self):
        mgr = ResourceLockManager()
        with pytest.raises(ValueError, match="Must provide at least one"):
            mgr.release("proj")

    def test_release_nonexistent_project(self):
        mgr = ResourceLockManager()
        released = mgr.release("proj", owner="agent-1")
        assert released == 0

    def test_release_no_matching_locks(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py"], "agent-1", "ca-42")
        released = mgr.release("proj", owner="agent-99")
        assert released == 0


class TestCheck:
    """Test conflict checking without acquiring."""

    def test_check_no_conflicts(self):
        mgr = ResourceLockManager()
        conflicts = mgr.check("proj", ["a.py"])
        assert conflicts == []

    def test_check_with_conflict(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py"], "agent-1", "ca-42")
        conflicts = mgr.check("proj", ["a.py"])
        assert len(conflicts) == 1

    def test_check_excludes_own_locks(self):
        """Owner's own locks don't count as conflicts."""
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py"], "agent-1", "ca-42")
        conflicts = mgr.check("proj", ["a.py"], owner="agent-1")
        assert conflicts == []

    def test_check_does_not_acquire(self):
        mgr = ResourceLockManager()
        mgr.check("proj", ["a.py"])
        locks = mgr.list_locks("proj")
        assert len(locks) == 0


class TestListLocks:
    """Test lock listing with filters."""

    def test_list_all_locks(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py", "b.py"], "agent-1", "ca-42")
        mgr.acquire("proj", ["c.py"], "agent-2", "ca-43")
        locks = mgr.list_locks("proj")
        assert len(locks) == 3

    def test_list_by_owner(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py", "b.py"], "agent-1", "ca-42")
        mgr.acquire("proj", ["c.py"], "agent-2", "ca-43")
        locks = mgr.list_locks("proj", owner="agent-1")
        assert len(locks) == 2
        assert all(l.owner == "agent-1" for l in locks)

    def test_list_by_work_item(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["a.py", "b.py"], "agent-1", "ca-42")
        mgr.acquire("proj", ["c.py"], "agent-1", "ca-43")
        locks = mgr.list_locks("proj", work_item_id="ca-42")
        assert len(locks) == 2

    def test_list_sorted_by_path(self):
        mgr = ResourceLockManager()
        mgr.acquire("proj", ["c.py", "a.py", "b.py"], "agent-1", "ca-42")
        locks = mgr.list_locks("proj")
        paths = [l.path for l in locks]
        assert paths == sorted(paths)

    def test_list_empty_project(self):
        mgr = ResourceLockManager()
        locks = mgr.list_locks("nonexistent")
        assert locks == []
