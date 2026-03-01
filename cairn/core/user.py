"""User identity, RBAC context, and authentication utilities.

Mirrors cairn/core/trace.py pattern — frozen dataclass + ContextVar.
When auth is disabled (default), current_user() returns None and all
scoping filters become no-ops.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UserContext — per-request identity propagation via contextvars
# ---------------------------------------------------------------------------

_user_ctx: ContextVar[UserContext | None] = ContextVar("_user_ctx", default=None)


@dataclass(frozen=True)
class UserContext:
    """Immutable user context propagated through an operation."""

    user_id: int
    username: str
    role: str  # "admin" | "user" | "agent"
    project_ids: frozenset[int] = field(default_factory=frozenset)


def set_user(ctx: UserContext) -> None:
    """Set the current user context."""
    _user_ctx.set(ctx)


def current_user() -> UserContext | None:
    """Read the current user context (or None if auth disabled / not set)."""
    return _user_ctx.get()


def clear_user() -> None:
    """Clear the user context. Call after the request completes."""
    _user_ctx.set(None)


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    import bcrypt
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: int,
    username: str,
    role: str,
    *,
    secret: str,
    expire_minutes: int = 1440,
) -> str:
    """Create a JWT access token."""
    import jwt

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str) -> dict | None:
    """Decode and validate a JWT. Returns payload dict or None on failure."""
    import jwt

    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except jwt.InvalidTokenError:
        logger.debug("Invalid JWT")
        return None


# ---------------------------------------------------------------------------
# UserManager — database operations for user CRUD and project membership
# ---------------------------------------------------------------------------

class UserManager:
    """Manages user accounts and project access."""

    def __init__(self, db: Database):
        self.db = db

    def is_first_user(self) -> bool:
        """Check if no users exist yet (for bootstrap admin)."""
        row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM users")
        return row["cnt"] == 0

    def create_user(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        role: str | None = None,
    ) -> dict:
        """Create a new user. First user auto-becomes admin."""
        if role is None:
            role = "admin" if self.is_first_user() else "user"

        pw_hash = hash_password(password)
        row = self.db.execute_one(
            """
            INSERT INTO users (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id, username, email, role, is_active, created_at
            """,
            (username, email, pw_hash, role),
        )
        self.db.commit()
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "is_active": row["is_active"],
            "created_at": row["created_at"].isoformat(),
        }

    def get_by_username(self, username: str) -> dict | None:
        """Fetch user by username (includes password_hash for auth)."""
        row = self.db.execute_one(
            "SELECT * FROM users WHERE username = %s", (username,),
        )
        if not row:
            return None
        return dict(row)

    def get_by_id(self, user_id: int) -> dict | None:
        """Fetch user by ID (excludes password_hash)."""
        row = self.db.execute_one(
            """
            SELECT id, username, email, role, is_active, created_at, updated_at
            FROM users WHERE id = %s
            """,
            (user_id,),
        )
        return dict(row) if row else None

    def list_users(self, limit: int = 50, offset: int = 0) -> dict:
        """List all users (admin endpoint)."""
        rows = self.db.execute(
            """
            SELECT id, username, email, role, is_active, created_at, updated_at,
                   COUNT(*) OVER() AS _total
            FROM users
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        total = rows[0]["_total"] if rows else 0
        items = [
            {
                "id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "role": r["role"],
                "is_active": r["is_active"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def update_user(
        self,
        user_id: int,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        email: str | None = None,
    ) -> dict | None:
        """Update user fields (admin endpoint)."""
        updates = []
        params = []
        if role is not None:
            updates.append("role = %s")
            params.append(role)
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if not updates:
            return self.get_by_id(user_id)

        updates.append("updated_at = NOW()")
        params.append(user_id)
        self.db.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )
        self.db.commit()
        return self.get_by_id(user_id)

    # --- Project membership ---

    def get_accessible_project_ids(self, user_id: int) -> set[int]:
        """Get the set of project IDs a user can access."""
        rows = self.db.execute(
            "SELECT project_id FROM user_projects WHERE user_id = %s",
            (user_id,),
        )
        return {r["project_id"] for r in rows}

    def add_project_member(
        self, user_id: int, project_id: int, role: str = "member",
    ) -> None:
        """Grant a user access to a project."""
        self.db.execute(
            """
            INSERT INTO user_projects (user_id, project_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, project_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (user_id, project_id, role),
        )
        self.db.commit()

    def remove_project_member(self, user_id: int, project_id: int) -> None:
        """Revoke a user's access to a project."""
        self.db.execute(
            "DELETE FROM user_projects WHERE user_id = %s AND project_id = %s",
            (user_id, project_id),
        )
        self.db.commit()

    def list_project_members(self, project_id: int) -> list[dict]:
        """List all members of a project."""
        rows = self.db.execute(
            """
            SELECT u.id, u.username, u.email, u.role AS user_role,
                   up.role AS project_role, up.granted_at
            FROM user_projects up
            JOIN users u ON u.id = up.user_id
            WHERE up.project_id = %s
            ORDER BY up.granted_at
            """,
            (project_id,),
        )
        return [
            {
                "user_id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "user_role": r["user_role"],
                "project_role": r["project_role"],
                "granted_at": r["granted_at"].isoformat(),
            }
            for r in rows
        ]

    def load_user_context(self, user_id: int) -> UserContext | None:
        """Build a UserContext from DB after JWT decode."""
        user = self.get_by_id(user_id)
        if not user or not user.get("is_active"):
            return None
        project_ids = self.get_accessible_project_ids(user_id)
        return UserContext(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            project_ids=frozenset(project_ids),
        )
