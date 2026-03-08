"""Lightweight MCP tool authorization helpers (ca-230).

First-pass authorization for MCP tools. NOT full RBAC — just basic checks:

1. **Project-scoped reads**: If the user has project_ids assigned, only allow
   access to those projects. Empty project_ids = unrestricted (backwards compat).

2. **Admin-only operations**: dispatch, consolidate, decay_scan require admin role.

3. **Safe degradation**: When auth is disabled (stdio mode, no auth middleware),
   all checks pass silently. This is intentional — single-user local mode
   should never be blocked.

Design decisions:
- Checks raise ValueError on denial (caught by existing tool error handlers).
- project_ids contains integer IDs but tools use project names. We resolve
  via a DB lookup (cached per-request via the contextvar lifecycle).
- __global__ project is always allowed (rules, cross-project data).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.user import UserContext, current_user

if TYPE_CHECKING:
    from cairn.core.services import Services

logger = logging.getLogger("cairn")


def _auth_enabled(svc: Services) -> bool:
    """Check if auth is enabled in config.

    Returns False if the auth config is missing (e.g., in tests with mock configs).
    """
    try:
        return bool(svc.config.auth.enabled)
    except AttributeError:
        return False


def require_auth(svc: Services) -> UserContext:
    """Get the current user or raise if auth is enabled and no user is set.

    When auth is disabled, returns a synthetic unrestricted context so callers
    can use the result without None checks.
    """
    ctx = current_user()
    if ctx is not None:
        return ctx
    if _auth_enabled(svc):
        raise ValueError("Authentication required")
    # Auth disabled — return a permissive sentinel (no restrictions)
    return UserContext(user_id=0, username="anonymous", role="admin", project_ids=frozenset())


def require_admin(svc: Services) -> UserContext:
    """Require admin role. Raises ValueError if not admin.

    When auth is disabled, passes silently (anonymous gets admin sentinel).
    """
    ctx = require_auth(svc)
    if ctx.role != "admin":
        raise ValueError(
            f"Admin access required (current role: {ctx.role})"
        )
    return ctx


def check_project_access(svc: Services, project: str | None) -> None:
    """Check if the current user can access the given project.

    Rules:
    - If project is None or '__global__', always allowed.
    - If auth is disabled, always allowed.
    - If user has no project_ids (empty frozenset), always allowed (backwards compat).
    - Otherwise, resolve project name to ID and check membership.

    Raises ValueError on denial.
    """
    if not project or project == "__global__":
        return

    ctx = current_user()
    if ctx is None:
        if _auth_enabled(svc):
            raise ValueError("Authentication required")
        return  # Auth disabled — allow all

    # No project restrictions assigned — allow all (backwards compat)
    if not ctx.project_ids:
        return

    # Admin bypasses project restrictions
    if ctx.role == "admin":
        return

    # Resolve project name to ID
    project_id = _resolve_project_id(svc, project)
    if project_id is None:
        # Project doesn't exist yet — allow (it may be created by this operation)
        return

    if project_id not in ctx.project_ids:
        raise ValueError(
            f"Access denied: you do not have access to project '{project}'"
        )


def _resolve_project_id(svc: Services, project_name: str) -> int | None:
    """Resolve a project name to its integer ID.

    Returns None if the project doesn't exist.
    """
    row = svc.db.execute_one(
        "SELECT id FROM projects WHERE name = %s", (project_name,)
    )
    return row["id"] if row else None
