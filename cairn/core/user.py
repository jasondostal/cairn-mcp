"""User identity, RBAC context, and authentication utilities.

Mirrors cairn/core/trace.py pattern — frozen dataclass + ContextVar.
When auth is disabled (default), current_user() returns None and all
scoping filters become no-ops.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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

    now = datetime.now(UTC)
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
        assert row is not None
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
        assert row is not None
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
        updates: list[str] = []
        params: list[str | int | bool] = []
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
        """Get project IDs a user can access (direct + group-based)."""
        rows = self.db.execute(
            """
            SELECT project_id FROM user_projects WHERE user_id = %s
            UNION
            SELECT gp.project_id FROM group_members gm
            JOIN group_projects gp ON gp.group_id = gm.group_id
            WHERE gm.user_id = %s
            """,
            (user_id, user_id),
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

    # --- Personal Access Tokens (PATs) ---

    def create_api_token(
        self,
        user_id: int,
        name: str,
        expires_at: datetime | None = None,
    ) -> dict:
        """Create a personal access token. Returns the raw token (shown once)."""
        import hashlib
        import secrets as _secrets

        raw_token = f"cairn_{_secrets.token_hex(24)}"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token_prefix = raw_token[:12]

        row = self.db.execute_one(
            """
            INSERT INTO api_tokens (user_id, name, token_hash, token_prefix, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, token_prefix, expires_at, created_at
            """,
            (user_id, name, token_hash, token_prefix, expires_at),
        )
        assert row is not None
        self.db.commit()
        return {
            "id": row["id"],
            "name": row["name"],
            "raw_token": raw_token,
            "token_prefix": row["token_prefix"],
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "created_at": row["created_at"].isoformat(),
        }

    def list_api_tokens(self, user_id: int) -> list[dict]:
        """List a user's API tokens (metadata only, no secrets)."""
        rows = self.db.execute(
            """
            SELECT id, name, token_prefix, expires_at, last_used_at, created_at, is_active
            FROM api_tokens WHERE user_id = %s ORDER BY created_at DESC
            """,
            (user_id,),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "token_prefix": r["token_prefix"],
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
                "created_at": r["created_at"].isoformat(),
                "is_active": r["is_active"],
            }
            for r in rows
        ]

    def revoke_api_token(self, token_id: int, user_id: int) -> bool:
        """Revoke a token (soft delete). Returns True if found and revoked."""
        self.db.execute(
            "UPDATE api_tokens SET is_active = FALSE WHERE id = %s AND user_id = %s",
            (token_id, user_id),
        )
        self.db.commit()
        return True

    def resolve_api_token(self, raw_token: str) -> UserContext | None:
        """Resolve a raw PAT to a UserContext. Updates last_used_at."""
        import hashlib

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        row = self.db.execute_one(
            """
            SELECT t.user_id, t.expires_at
            FROM api_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token_hash = %s AND t.is_active = TRUE AND u.is_active = TRUE
            """,
            (token_hash,),
        )
        if not row:
            return None
        if row["expires_at"] and row["expires_at"] < datetime.now(UTC):
            return None
        # Update last_used_at
        self.db.execute(
            "UPDATE api_tokens SET last_used_at = NOW() WHERE token_hash = %s",
            (token_hash,),
        )
        self.db.commit()
        return self.load_user_context(row["user_id"])

    # --- OIDC users ---

    def get_by_external_id(self, auth_provider: str, external_id: str) -> dict | None:
        """Find a user by their external IdP identity."""
        row = self.db.execute_one(
            "SELECT * FROM users WHERE auth_provider = %s AND external_id = %s",
            (auth_provider, external_id),
        )
        return dict(row) if row else None

    def create_oidc_user(
        self,
        external_id: str,
        username: str,
        email: str | None = None,
        role: str = "user",
    ) -> dict:
        """Create a user from OIDC claims (no password)."""
        row = self.db.execute_one(
            """
            INSERT INTO users (username, email, password_hash, role, auth_provider, external_id)
            VALUES (%s, %s, NULL, %s, 'oidc', %s)
            RETURNING id, username, email, role, is_active, created_at
            """,
            (username, email, role, external_id),
        )
        assert row is not None
        self.db.commit()
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "is_active": row["is_active"],
            "created_at": row["created_at"].isoformat(),
        }

    # --- Groups ---

    def create_group(self, name: str, description: str = "", source: str = "manual") -> dict:
        """Create a new group."""
        row = self.db.execute_one(
            """
            INSERT INTO groups (name, description, source)
            VALUES (%s, %s, %s)
            RETURNING id, name, description, source, created_at, updated_at
            """,
            (name, description, source),
        )
        assert row is not None
        self.db.commit()
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "source": row["source"], "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    def get_group(self, group_id: int) -> dict | None:
        """Fetch a group by ID."""
        row = self.db.execute_one(
            "SELECT id, name, description, source, created_at, updated_at FROM groups WHERE id = %s",
            (group_id,),
        )
        if not row:
            return None
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "source": row["source"], "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    def get_group_by_name(self, name: str) -> dict | None:
        """Fetch a group by name."""
        row = self.db.execute_one(
            "SELECT id, name, description, source, created_at, updated_at FROM groups WHERE name = %s",
            (name,),
        )
        if not row:
            return None
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "source": row["source"], "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    def list_groups(self, limit: int = 50, offset: int = 0) -> dict:
        """List all groups with member/project counts."""
        rows = self.db.execute(
            """
            SELECT g.id, g.name, g.description, g.source, g.created_at, g.updated_at,
                   (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id) AS member_count,
                   (SELECT COUNT(*) FROM group_projects gp WHERE gp.group_id = g.id) AS project_count,
                   COUNT(*) OVER() AS _total
            FROM groups g
            ORDER BY g.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        total = rows[0]["_total"] if rows else 0
        items = [
            {
                "id": r["id"], "name": r["name"], "description": r["description"],
                "source": r["source"], "member_count": r["member_count"],
                "project_count": r["project_count"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def update_group(self, group_id: int, *, name: str | None = None, description: str | None = None) -> dict | None:
        """Update group fields."""
        updates: list[str] = []
        params: list[str | int] = []
        if name is not None:
            updates.append("name = %s")
            params.append(name)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if not updates:
            return self.get_group(group_id)
        updates.append("updated_at = NOW()")
        params.append(group_id)
        self.db.execute(
            f"UPDATE groups SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )
        self.db.commit()
        return self.get_group(group_id)

    def delete_group(self, group_id: int) -> bool:
        """Delete a group (cascades members and projects)."""
        self.db.execute("DELETE FROM groups WHERE id = %s", (group_id,))
        self.db.commit()
        return True

    def add_group_member(self, group_id: int, user_id: int) -> None:
        """Add a user to a group."""
        self.db.execute(
            """
            INSERT INTO group_members (group_id, user_id)
            VALUES (%s, %s)
            ON CONFLICT (group_id, user_id) DO NOTHING
            """,
            (group_id, user_id),
        )
        self.db.commit()

    def remove_group_member(self, group_id: int, user_id: int) -> None:
        """Remove a user from a group."""
        self.db.execute(
            "DELETE FROM group_members WHERE group_id = %s AND user_id = %s",
            (group_id, user_id),
        )
        self.db.commit()

    def list_group_members(self, group_id: int) -> list[dict]:
        """List members of a group."""
        rows = self.db.execute(
            """
            SELECT u.id, u.username, u.email, u.role, gm.added_at
            FROM group_members gm
            JOIN users u ON u.id = gm.user_id
            WHERE gm.group_id = %s
            ORDER BY gm.added_at
            """,
            (group_id,),
        )
        return [
            {
                "user_id": r["id"], "username": r["username"], "email": r["email"],
                "role": r["role"], "added_at": r["added_at"].isoformat(),
            }
            for r in rows
        ]

    def add_group_project(self, group_id: int, project_id: int, role: str = "member") -> None:
        """Assign a project to a group."""
        self.db.execute(
            """
            INSERT INTO group_projects (group_id, project_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (group_id, project_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (group_id, project_id, role),
        )
        self.db.commit()

    def remove_group_project(self, group_id: int, project_id: int) -> None:
        """Remove a project from a group."""
        self.db.execute(
            "DELETE FROM group_projects WHERE group_id = %s AND project_id = %s",
            (group_id, project_id),
        )
        self.db.commit()

    def list_group_projects(self, group_id: int) -> list[dict]:
        """List projects assigned to a group."""
        rows = self.db.execute(
            """
            SELECT p.id, p.name, gp.role, gp.granted_at
            FROM group_projects gp
            JOIN projects p ON p.id = gp.project_id
            WHERE gp.group_id = %s
            ORDER BY gp.granted_at
            """,
            (group_id,),
        )
        return [
            {
                "project_id": r["id"], "project_name": r["name"],
                "role": r["role"], "granted_at": r["granted_at"].isoformat(),
            }
            for r in rows
        ]

    def get_user_groups(self, user_id: int) -> list[dict]:
        """List groups a user belongs to."""
        rows = self.db.execute(
            """
            SELECT g.id, g.name, g.description, g.source, gm.added_at
            FROM group_members gm
            JOIN groups g ON g.id = gm.group_id
            WHERE gm.user_id = %s
            ORDER BY g.name
            """,
            (user_id,),
        )
        return [
            {
                "id": r["id"], "name": r["name"], "description": r["description"],
                "source": r["source"], "added_at": r["added_at"].isoformat(),
            }
            for r in rows
        ]

    def sync_oidc_groups(self, user_id: int, group_names: list[str]) -> None:
        """Sync OIDC group claims — create missing groups, update membership."""
        if not group_names:
            # Remove from all OIDC groups
            self.db.execute(
                """
                DELETE FROM group_members
                WHERE user_id = %s AND group_id IN (
                    SELECT id FROM groups WHERE source = 'oidc'
                )
                """,
                (user_id,),
            )
            self.db.commit()
            return

        # Ensure all claimed groups exist
        for name in group_names:
            existing = self.get_group_by_name(name)
            if not existing:
                self.create_group(name, source="oidc")

        # Get IDs of claimed groups
        placeholders = ",".join(["%s"] * len(group_names))
        claimed_rows = self.db.execute(
            f"SELECT id FROM groups WHERE name IN ({placeholders})",
            tuple(group_names),
        )
        claimed_ids = {r["id"] for r in claimed_rows}

        # Current OIDC group memberships
        current_rows = self.db.execute(
            """
            SELECT gm.group_id FROM group_members gm
            JOIN groups g ON g.id = gm.group_id
            WHERE gm.user_id = %s AND g.source = 'oidc'
            """,
            (user_id,),
        )
        current_ids = {r["group_id"] for r in current_rows}

        # Add to new groups
        for gid in claimed_ids - current_ids:
            self.add_group_member(gid, user_id)

        # Remove from groups no longer claimed
        for gid in current_ids - claimed_ids:
            self.remove_group_member(gid, user_id)

    # --- OIDC users ---

    def get_or_create_oidc_user(
        self,
        external_id: str,
        claims: dict,
        *,
        default_role: str = "user",
        admin_groups: list[str] | None = None,
    ) -> dict:
        """Find or create a user from OIDC claims.

        Link order: external_id match → email match (link existing) → create new.
        """
        # 1. Already linked by external_id
        existing = self.get_by_external_id("oidc", external_id)
        if existing:
            if claims.get("email") and claims["email"] != existing.get("email"):
                self.update_user(existing["id"], email=claims["email"])
            return self.get_by_id(existing["id"]) or existing

        # Determine role from groups
        role = default_role
        if admin_groups:
            user_groups = claims.get("groups", [])
            if any(g in admin_groups for g in user_groups):
                role = "admin"

        # 2. Email match — link existing local user to this OIDC identity
        email = claims.get("email")
        if email:
            email_match = self.db.execute_one(
                "SELECT * FROM users WHERE email = %s AND is_active = TRUE",
                (email,),
            )
            if email_match:
                self.db.execute(
                    "UPDATE users SET auth_provider = 'oidc', external_id = %s WHERE id = %s",
                    (external_id, email_match["id"]),
                )
                if role == "admin" and email_match.get("role") != "admin":
                    self.db.execute(
                        "UPDATE users SET role = 'admin' WHERE id = %s",
                        (email_match["id"],),
                    )
                self.db.commit()
                logger.info("Linked OIDC identity to existing user %s (email match)", email_match["username"])
                return self.get_by_id(email_match["id"]) or email_match

        # 3. Create new OIDC user
        username = (
            claims.get("preferred_username")
            or (email.split("@")[0] if email else "")
            or f"oidc_{external_id[:8]}"
        )

        # Handle username collision
        base_username = username
        counter = 1
        while self.get_by_username(username):
            username = f"{base_username}_{counter}"
            counter += 1

        return self.create_oidc_user(
            external_id=external_id,
            username=username,
            email=email,
            role=role,
        )
