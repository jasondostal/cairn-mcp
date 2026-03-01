"""Tests for RBAC query scoping — ensures user context filters work correctly.

When current_user() is None (auth disabled), no filtering occurs.
When set, non-admin users only see their accessible projects.
"""

from unittest.mock import MagicMock, patch
import pytest

from cairn.core.user import (
    UserContext,
    set_user,
    current_user,
    clear_user,
)


class TestSearchEngineScoping:
    """SearchEngine._build_filters() adds user project filter."""

    def setup_method(self):
        clear_user()

    def teardown_method(self):
        clear_user()

    def test_no_user_no_filter(self):
        """Auth disabled: no user context, no project filter."""
        from cairn.core.search import SearchEngine

        db = MagicMock()
        embedding = MagicMock()
        engine = SearchEngine(db, embedding)
        clauses, params = engine._build_filters(None, None)
        assert "project_id = ANY" not in clauses

    def test_admin_no_filter(self):
        """Admin users see everything."""
        from cairn.core.search import SearchEngine

        set_user(UserContext(user_id=1, username="admin", role="admin", project_ids=frozenset({1})))
        db = MagicMock()
        embedding = MagicMock()
        engine = SearchEngine(db, embedding)
        clauses, params = engine._build_filters(None, None)
        assert "project_id = ANY" not in clauses

    def test_user_gets_filter(self):
        """Regular user gets project filter."""
        from cairn.core.search import SearchEngine

        set_user(UserContext(user_id=2, username="alice", role="user", project_ids=frozenset({10, 20})))
        db = MagicMock()
        embedding = MagicMock()
        engine = SearchEngine(db, embedding)
        clauses, params = engine._build_filters(None, None)
        assert "m.project_id = ANY(%s)" in clauses
        # Should have the project IDs in params
        assert any(isinstance(p, list) and set(p) == {10, 20} for p in params)

    def test_agent_gets_filter(self):
        """Agent users also get project filter."""
        from cairn.core.search import SearchEngine

        set_user(UserContext(user_id=3, username="bot", role="agent", project_ids=frozenset({5})))
        db = MagicMock()
        embedding = MagicMock()
        engine = SearchEngine(db, embedding)
        clauses, params = engine._build_filters(None, None)
        assert "m.project_id = ANY(%s)" in clauses


class TestMemoryModifyScoping:
    """memory.modify() checks project access."""

    def setup_method(self):
        clear_user()

    def teardown_method(self):
        clear_user()

    def test_no_user_no_check(self):
        """Without user context, modify proceeds without access check."""
        from cairn.core.memory import MemoryStore

        db = MagicMock()
        embedding = MagicMock()
        store = MemoryStore(db, embedding)
        db.execute_one.return_value = None
        db.execute.return_value = None
        # Should not fail — no user = no RBAC check
        store.modify(1, "inactivate", reason="test")

    def test_admin_bypasses_check(self):
        """Admin can modify any memory."""
        from cairn.core.memory import MemoryStore

        set_user(UserContext(user_id=1, username="admin", role="admin"))
        db = MagicMock()
        embedding = MagicMock()
        store = MemoryStore(db, embedding)
        db.execute.return_value = None
        store.modify(1, "inactivate", reason="test")
        # Should have executed the UPDATE (not blocked)
        assert db.execute.called

    def test_user_blocked_on_wrong_project(self):
        """User cannot modify memory in a project they don't have access to."""
        from cairn.core.memory import MemoryStore

        set_user(UserContext(user_id=2, username="alice", role="user", project_ids=frozenset({10})))
        db = MagicMock()
        embedding = MagicMock()
        store = MemoryStore(db, embedding)
        # Memory belongs to project 99 (not in user's set)
        db.execute_one.return_value = {"project_id": 99}
        result = store.modify(1, "inactivate", reason="test")
        assert result.get("error") == "Access denied"


class TestGetRulesScoping:
    """get_rules() adds personal rules project when user is set."""

    def setup_method(self):
        clear_user()

    def teardown_method(self):
        clear_user()

    def test_no_user_global_only(self):
        """Without user context, returns __global__ + project rules."""
        from cairn.core.memory import MemoryStore

        db = MagicMock()
        embedding = MagicMock()
        store = MemoryStore(db, embedding)
        db.execute_one.return_value = {"total": 0}
        db.execute.return_value = []
        store.get_rules("myproject")
        # Check the query was called with project names including __global__
        call_args = db.execute_one.call_args[0]
        assert "__global__" in call_args[1][0]

    def test_user_gets_personal_rules(self):
        """With user context, __personal__:<username> is included."""
        from cairn.core.memory import MemoryStore

        set_user(UserContext(user_id=2, username="alice", role="user"))
        db = MagicMock()
        embedding = MagicMock()
        store = MemoryStore(db, embedding)
        db.execute_one.return_value = {"total": 0}
        db.execute.return_value = []
        store.get_rules("myproject")
        # Check that __personal__:alice was included
        call_args = db.execute_one.call_args[0]
        project_names = call_args[1][0]
        assert "__personal__:alice" in project_names
        assert "__global__" in project_names


class TestWorkItemScoping:
    """work_items.list_items() scopes to user projects."""

    def setup_method(self):
        clear_user()

    def teardown_method(self):
        clear_user()

    def test_no_user_no_filter(self):
        """Without user, list_items has no RBAC filter."""
        from cairn.core.work_items import WorkItemManager

        db = MagicMock()
        embedding = MagicMock()
        mgr = WorkItemManager(db, embedding)
        db.execute.return_value = []
        mgr.list_items()
        # Check the query was called — no project_id = ANY in conditions
        call_query = db.execute.call_args[0][0]
        assert "project_id = ANY" not in call_query

    def test_user_gets_filter(self):
        """With user context, list_items filters to user's projects."""
        from cairn.core.work_items import WorkItemManager

        set_user(UserContext(user_id=2, username="alice", role="user", project_ids=frozenset({10, 20})))
        db = MagicMock()
        embedding = MagicMock()
        mgr = WorkItemManager(db, embedding)
        db.execute.return_value = []
        mgr.list_items()
        call_query = db.execute.call_args[0][0]
        assert "project_id = ANY" in call_query

    def test_admin_no_filter(self):
        """Admin sees all work items."""
        from cairn.core.work_items import WorkItemManager

        set_user(UserContext(user_id=1, username="admin", role="admin"))
        db = MagicMock()
        embedding = MagicMock()
        mgr = WorkItemManager(db, embedding)
        db.execute.return_value = []
        mgr.list_items()
        call_query = db.execute.call_args[0][0]
        assert "project_id = ANY" not in call_query


class TestProjectOwnershipOnCreate:
    """get_or_create_project() auto-adds creator as owner."""

    def setup_method(self):
        clear_user()

    def teardown_method(self):
        clear_user()

    def test_no_user_no_ownership(self):
        """Without user context, no user_projects row created."""
        from cairn.core.utils import get_or_create_project

        db = MagicMock()
        # get_project returns None (new project)
        db.execute_one.side_effect = [
            None,  # get_project
            None,  # _generate_prefix: collision check
            {"id": 42},  # INSERT RETURNING
        ]
        db.execute.return_value = []
        get_or_create_project(db, "new-project")
        # Should NOT have inserted into user_projects
        insert_calls = [
            c for c in db.execute.call_args_list
            if "user_projects" in str(c)
        ]
        assert len(insert_calls) == 0

    def test_user_gets_ownership(self):
        """With user context, creator is auto-added as project owner."""
        from cairn.core.utils import get_or_create_project

        set_user(UserContext(user_id=7, username="alice", role="user"))
        db = MagicMock()
        db.execute_one.side_effect = [
            None,  # get_project
            None,  # _generate_prefix
            {"id": 42},  # INSERT RETURNING
        ]
        get_or_create_project(db, "new-project")
        # Should have inserted into user_projects
        insert_calls = [
            c for c in db.execute.call_args_list
            if "user_projects" in str(c)
        ]
        assert len(insert_calls) == 1
