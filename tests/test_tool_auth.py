"""Tests for MCP tool authorization helpers (ca-230).

Verifies project-scoped access checks and admin-only operation guards.
"""

import pytest
from dataclasses import dataclass, field
from unittest.mock import MagicMock

from cairn.core.user import UserContext, set_user, clear_user
from cairn.tools.auth import (
    require_auth,
    require_admin,
    check_project_access,
    _auth_enabled,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MockAuthConfig:
    enabled: bool = False


@dataclass
class MockConfig:
    auth: MockAuthConfig = field(default_factory=MockAuthConfig)


def _make_svc(auth_enabled: bool = False) -> MagicMock:
    svc = MagicMock()
    svc.config = MockConfig(auth=MockAuthConfig(enabled=auth_enabled))
    return svc


@pytest.fixture(autouse=True)
def _clear_user_ctx():
    """Ensure user context is cleared after each test."""
    yield
    clear_user()


# ---------------------------------------------------------------------------
# _auth_enabled
# ---------------------------------------------------------------------------

class TestAuthEnabled:
    def test_returns_false_when_disabled(self):
        svc = _make_svc(auth_enabled=False)
        assert _auth_enabled(svc) is False

    def test_returns_true_when_enabled(self):
        svc = _make_svc(auth_enabled=True)
        assert _auth_enabled(svc) is True

    def test_returns_false_when_no_auth_config(self):
        svc = MagicMock()
        svc.config = object()  # no .auth attribute
        assert _auth_enabled(svc) is False


# ---------------------------------------------------------------------------
# require_auth
# ---------------------------------------------------------------------------

class TestRequireAuth:
    def test_returns_user_when_set(self):
        svc = _make_svc(auth_enabled=True)
        user = UserContext(user_id=1, username="alice", role="user")
        set_user(user)
        assert require_auth(svc) is user

    def test_raises_when_auth_enabled_no_user(self):
        svc = _make_svc(auth_enabled=True)
        with pytest.raises(ValueError, match="Authentication required"):
            require_auth(svc)

    def test_returns_sentinel_when_auth_disabled(self):
        svc = _make_svc(auth_enabled=False)
        ctx = require_auth(svc)
        assert ctx.user_id == 0
        assert ctx.username == "anonymous"
        assert ctx.role == "admin"


# ---------------------------------------------------------------------------
# require_admin
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    def test_passes_for_admin(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="admin"))
        ctx = require_admin(svc)
        assert ctx.role == "admin"

    def test_rejects_non_admin(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=2, username="bob", role="user"))
        with pytest.raises(ValueError, match="Admin access required"):
            require_admin(svc)

    def test_passes_when_auth_disabled(self):
        svc = _make_svc(auth_enabled=False)
        # No user set, auth disabled — should get admin sentinel
        ctx = require_admin(svc)
        assert ctx.role == "admin"

    def test_rejects_agent_role(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=3, username="agent-1", role="agent"))
        with pytest.raises(ValueError, match="Admin access required"):
            require_admin(svc)


# ---------------------------------------------------------------------------
# check_project_access
# ---------------------------------------------------------------------------

class TestCheckProjectAccess:
    def test_none_project_always_allowed(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset({10})))
        # Should not raise
        check_project_access(svc, None)

    def test_global_project_always_allowed(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset({10})))
        check_project_access(svc, "__global__")

    def test_empty_project_ids_allows_all(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset()))
        # No project restrictions — should allow any project
        check_project_access(svc, "secret-project")

    def test_admin_bypasses_project_check(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="admin", project_ids=frozenset({10})))
        # Admin should access any project even if not in project_ids
        check_project_access(svc, "other-project")

    def test_user_with_matching_project_allowed(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset({42})))
        # Mock DB to return project ID 42 for "my-project"
        svc.db.execute_one.return_value = {"id": 42}
        check_project_access(svc, "my-project")

    def test_user_without_matching_project_denied(self):
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset({42})))
        # Mock DB to return project ID 99 (not in user's project_ids)
        svc.db.execute_one.return_value = {"id": 99}
        with pytest.raises(ValueError, match="Access denied.*secret-project"):
            check_project_access(svc, "secret-project")

    def test_nonexistent_project_allowed(self):
        """Projects that don't exist yet should be allowed (may be created by this operation)."""
        svc = _make_svc(auth_enabled=True)
        set_user(UserContext(user_id=1, username="alice", role="user", project_ids=frozenset({42})))
        svc.db.execute_one.return_value = None  # project doesn't exist
        check_project_access(svc, "new-project")

    def test_auth_disabled_no_user_allows_all(self):
        svc = _make_svc(auth_enabled=False)
        # No user set, auth disabled
        check_project_access(svc, "any-project")

    def test_auth_enabled_no_user_raises(self):
        svc = _make_svc(auth_enabled=True)
        with pytest.raises(ValueError, match="Authentication required"):
            check_project_access(svc, "some-project")
