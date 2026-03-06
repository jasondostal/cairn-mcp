"""Authentication and user management REST endpoints (ca-124, ca-162)."""

from __future__ import annotations

import logging
from datetime import UTC

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from cairn.core.services import Services
from cairn.core.user import (
    UserManager,
    create_access_token,
    current_user,
    verify_password,
)
from cairn.core.utils import get_project

logger = logging.getLogger(__name__)


# --- Request models ---

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    role: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    email: str | None = None


class AddMemberRequest(BaseModel):
    user_id: int
    role: str = "member"


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupMemberRequest(BaseModel):
    user_id: int


class GroupProjectRequest(BaseModel):
    project_name: str
    role: str = "member"


class CreateTokenRequest(BaseModel):
    name: str
    expires_in_days: int | None = None  # None = never expires


def register_routes(router: APIRouter, svc: Services) -> None:
    """Register auth endpoints."""
    user_mgr: UserManager | None = svc.user_manager
    config = svc.config

    def _require_auth_enabled() -> JSONResponse | None:
        if not config.auth.enabled or not config.auth.jwt_secret:
            return JSONResponse(
                status_code=404,
                content={"detail": "Authentication is not enabled"},
            )
        if user_mgr is None:
            return JSONResponse(
                status_code=500,
                content={"detail": "UserManager not initialized"},
            )
        return None

    def _checked_mgr() -> UserManager:
        """Return user_mgr after auth is verified (narrows Optional type)."""
        assert user_mgr is not None
        return user_mgr

    def _require_admin():
        ctx = current_user()
        if not ctx or ctx.role != "admin":
            return JSONResponse(
                status_code=403,
                content={"detail": "Admin access required"},
            )
        return None

    # --- Public endpoints ---

    @router.post("/auth/register")
    def register(body: RegisterRequest):
        err = _require_auth_enabled()
        if err:
            return err

        # Check if user already exists
        existing = _checked_mgr().get_by_username(body.username)
        if existing:
            return JSONResponse(
                status_code=409,
                content={"detail": "Username already taken"},
            )

        user = _checked_mgr().create_user(
            body.username, body.password, email=body.email,
        )
        token = create_access_token(
            user["id"], user["username"], user["role"],
            secret=config.auth.jwt_secret,
            expire_minutes=config.auth.jwt_expire_minutes,
        )
        return {"user": user, "access_token": token, "token_type": "bearer"}

    @router.post("/auth/login")
    def login(body: LoginRequest):
        err = _require_auth_enabled()
        if err:
            return err

        user = _checked_mgr().get_by_username(body.username)
        if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
            )
        if not user.get("is_active", True):
            return JSONResponse(
                status_code=403,
                content={"detail": "Account is deactivated"},
            )

        token = create_access_token(
            user["id"], user["username"], user["role"],
            secret=config.auth.jwt_secret,
            expire_minutes=config.auth.jwt_expire_minutes,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
            },
        }

    @router.get("/auth/me")
    def get_me():
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        user = _checked_mgr().get_by_id(ctx.user_id)
        if not user:
            return JSONResponse(status_code=404, content={"detail": "User not found"})

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user.get("email"),
            "role": user["role"],
            "is_active": user["is_active"],
        }

    @router.get("/auth/status")
    def auth_status():
        """Public endpoint: auth configuration status."""
        enabled = config.auth.enabled and bool(config.auth.jwt_secret)
        has_users = True
        if enabled and user_mgr:
            has_users = not _checked_mgr().is_first_user()
        oidc_enabled = (
            config.auth.oidc.enabled
            and bool(config.auth.oidc.provider_url)
        )
        providers = ["local"]
        if oidc_enabled:
            providers.append("oidc")
        return {
            "enabled": enabled,
            "has_users": has_users,
            "oidc_enabled": oidc_enabled,
            "providers": providers,
        }

    # --- Admin endpoints ---

    @router.post("/auth/users")
    def create_user(body: CreateUserRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        existing = _checked_mgr().get_by_username(body.username)
        if existing:
            return JSONResponse(
                status_code=409,
                content={"detail": "Username already taken"},
            )

        user = _checked_mgr().create_user(
            body.username, body.password, email=body.email, role=body.role,
        )
        return user

    @router.get("/auth/users")
    def list_users(limit: int = 50, offset: int = 0):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        return _checked_mgr().list_users(limit=limit, offset=offset)

    @router.patch("/auth/users/{user_id}")
    def update_user(user_id: int, body: UpdateUserRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        result = _checked_mgr().update_user(
            user_id, role=body.role, is_active=body.is_active, email=body.email,
        )
        if not result:
            return JSONResponse(status_code=404, content={"detail": "User not found"})
        return result

    # --- OIDC/OAuth2 endpoints ---

    # Lazy-init: created on first OIDC request
    _oidc_client = None
    _oidc_state_store = None

    def _get_oidc():
        nonlocal _oidc_client, _oidc_state_store
        if _oidc_client is None:
            from cairn.core.oidc import OIDCClient, OIDCStateStore
            oidc_cfg = config.auth.oidc
            _oidc_client = OIDCClient(
                provider_url=oidc_cfg.provider_url,
                client_id=oidc_cfg.client_id,
                client_secret=oidc_cfg.client_secret,
                scopes=oidc_cfg.scopes,
            )
            _oidc_state_store = OIDCStateStore()
        return _oidc_client, _oidc_state_store

    @router.get("/auth/oidc/login")
    def oidc_login(redirect_uri: str | None = None):
        """Start OIDC login flow. Returns the authorization URL to redirect to."""
        err = _require_auth_enabled()
        if err:
            return err
        if not config.auth.oidc.enabled or not config.auth.oidc.provider_url:
            return JSONResponse(status_code=404, content={"detail": "OIDC not configured"})

        oidc, state_store = _get_oidc()
        # Callback URL: prefer explicit redirect_uri, then CAIRN_PUBLIC_URL, then internal host
        if redirect_uri:
            callback_uri = redirect_uri
        elif config.public_url:
            callback_uri = f"{config.public_url.rstrip('/')}/api/auth/oidc/callback"
        else:
            callback_uri = f"http://{config.http_host}:{config.http_port}/api/auth/oidc/callback"
        # Extract UI origin from callback URI (e.g. http://localhost:3000)
        # so we can redirect back correctly even behind a rewriting proxy.
        from urllib.parse import urlparse
        parsed = urlparse(callback_uri)
        ui_origin = f"{parsed.scheme}://{parsed.netloc}"
        state, code_verifier = state_store.create(ui_origin)
        auth_url = oidc.authorization_url(callback_uri, state, code_verifier)
        return {"authorization_url": auth_url, "state": state}

    @router.get("/auth/oidc/callback")
    def oidc_callback(code: str, state: str, request: Request):
        """Handle OIDC provider callback. Exchanges code for tokens, creates/finds user."""
        err = _require_auth_enabled()
        if err:
            return err
        if not config.auth.oidc.enabled:
            return JSONResponse(status_code=404, content={"detail": "OIDC not configured"})

        oidc, state_store = _get_oidc()
        state_data = state_store.consume(state)
        if state_data is None:
            return JSONResponse(status_code=400, content={"detail": "Invalid or expired state"})
        code_verifier, ui_origin = state_data

        try:
            # Reconstruct callback URI using the stored origin (proxy-safe)
            callback_uri = f"{ui_origin}{request.url.path}"

            # Exchange code for tokens
            token_response = oidc.exchange_code(code, callback_uri, code_verifier)
            id_token = token_response.get("id_token")
            if not id_token:
                return JSONResponse(status_code=400, content={"detail": "No id_token in response"})

            # Validate ID token
            claims = oidc.validate_id_token(id_token)
            external_id = claims.get("sub")
            if not external_id:
                return JSONResponse(status_code=400, content={"detail": "No sub claim in ID token"})

            # Get or create user
            oidc_cfg = config.auth.oidc
            admin_groups = [g.strip() for g in oidc_cfg.admin_groups.split(",") if g.strip()] if oidc_cfg.admin_groups else None
            user = _checked_mgr().get_or_create_oidc_user(
                external_id=external_id,
                claims=claims,
                default_role=oidc_cfg.default_role,
                admin_groups=admin_groups,
            )

            # Sync OIDC group memberships
            oidc_groups = claims.get("groups", [])
            if isinstance(oidc_groups, list) and oidc_groups:
                try:
                    _checked_mgr().sync_oidc_groups(user["id"], oidc_groups)
                except Exception:
                    logger.warning("OIDC group sync failed for user %s", user["id"], exc_info=True)

            # Issue Cairn JWT
            cairn_token = create_access_token(
                user["id"], user["username"], user["role"],
                secret=config.auth.jwt_secret,
                expire_minutes=config.auth.jwt_expire_minutes,
            )

            redirect_url = f"{ui_origin}/login?token={cairn_token}&username={user['username']}&role={user['role']}"
            return RedirectResponse(url=redirect_url, status_code=302)

        except Exception:
            logger.exception("OIDC callback failed")
            return JSONResponse(status_code=500, content={"detail": "OIDC authentication failed"})

    # --- Project membership endpoints ---

    @router.post("/projects/{project_name}/members")
    def add_project_member(project_name: str, body: AddMemberRequest):
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        project_id = get_project(svc.db, project_name)
        if project_id is None:
            return JSONResponse(status_code=404, content={"detail": "Project not found"})

        # Only admin or project owner can add members
        if ctx.role != "admin":
            members = _checked_mgr().list_project_members(project_id)
            is_owner = any(
                m["user_id"] == ctx.user_id and m["project_role"] == "owner"
                for m in members
            )
            if not is_owner:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Only project owners or admins can add members"},
                )

        _checked_mgr().add_project_member(body.user_id, project_id, body.role)
        return {"status": "ok"}

    @router.delete("/projects/{project_name}/members/{member_user_id}")
    def remove_project_member(project_name: str, member_user_id: int):
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        project_id = get_project(svc.db, project_name)
        if project_id is None:
            return JSONResponse(status_code=404, content={"detail": "Project not found"})

        if ctx.role != "admin":
            members = _checked_mgr().list_project_members(project_id)
            is_owner = any(
                m["user_id"] == ctx.user_id and m["project_role"] == "owner"
                for m in members
            )
            if not is_owner:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Only project owners or admins can remove members"},
                )

        _checked_mgr().remove_project_member(member_user_id, project_id)
        return {"status": "ok"}

    # --- Personal Access Tokens ---

    @router.post("/auth/tokens")
    def create_token(body: CreateTokenRequest):
        """Create a personal access token for the current user."""
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        from datetime import datetime, timedelta
        expires_at = None
        if body.expires_in_days:
            expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

        result = _checked_mgr().create_api_token(ctx.user_id, body.name, expires_at)
        return result

    @router.get("/auth/tokens")
    def list_tokens():
        """List the current user's API tokens (no secrets)."""
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        return _checked_mgr().list_api_tokens(ctx.user_id)

    @router.delete("/auth/tokens/{token_id}")
    def revoke_token(token_id: int):
        """Revoke a personal access token."""
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        _checked_mgr().revoke_api_token(token_id, ctx.user_id)
        return {"status": "ok"}

    @router.get("/projects/{project_name}/members")
    def list_project_members(project_name: str):
        err = _require_auth_enabled()
        if err:
            return err

        ctx = current_user()
        if not ctx:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        project_id = get_project(svc.db, project_name)
        if project_id is None:
            return JSONResponse(status_code=404, content={"detail": "Project not found"})

        # Admin sees all; members can see their own project's member list
        if ctx.role != "admin" and project_id not in ctx.project_ids:
            return JSONResponse(
                status_code=403,
                content={"detail": "Not a member of this project"},
            )

        return _checked_mgr().list_project_members(project_id)

    # --- Group management (ca-171) ---

    @router.post("/auth/groups")
    def create_group(body: CreateGroupRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        existing = _checked_mgr().get_group_by_name(body.name)
        if existing:
            return JSONResponse(status_code=409, content={"detail": "Group name already taken"})

        return _checked_mgr().create_group(body.name, body.description)

    @router.get("/auth/groups")
    def list_groups(limit: int = 50, offset: int = 0):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        return _checked_mgr().list_groups(limit=limit, offset=offset)

    @router.get("/auth/groups/{group_id}")
    def get_group(group_id: int):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        group = _checked_mgr().get_group(group_id)
        if not group:
            return JSONResponse(status_code=404, content={"detail": "Group not found"})

        group["members"] = _checked_mgr().list_group_members(group_id)
        group["projects"] = _checked_mgr().list_group_projects(group_id)
        return group

    @router.patch("/auth/groups/{group_id}")
    def update_group(group_id: int, body: UpdateGroupRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        group = _checked_mgr().get_group(group_id)
        if not group:
            return JSONResponse(status_code=404, content={"detail": "Group not found"})

        result = _checked_mgr().update_group(group_id, name=body.name, description=body.description)
        return result

    @router.delete("/auth/groups/{group_id}")
    def delete_group(group_id: int):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        group = _checked_mgr().get_group(group_id)
        if not group:
            return JSONResponse(status_code=404, content={"detail": "Group not found"})

        _checked_mgr().delete_group(group_id)
        return {"status": "ok"}

    @router.post("/auth/groups/{group_id}/members")
    def add_group_member(group_id: int, body: GroupMemberRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        group = _checked_mgr().get_group(group_id)
        if not group:
            return JSONResponse(status_code=404, content={"detail": "Group not found"})

        user = _checked_mgr().get_by_id(body.user_id)
        if not user:
            return JSONResponse(status_code=404, content={"detail": "User not found"})

        _checked_mgr().add_group_member(group_id, body.user_id)
        return {"status": "ok"}

    @router.delete("/auth/groups/{group_id}/members/{member_user_id}")
    def remove_group_member(group_id: int, member_user_id: int):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        _checked_mgr().remove_group_member(group_id, member_user_id)
        return {"status": "ok"}

    @router.post("/auth/groups/{group_id}/projects")
    def add_group_project(group_id: int, body: GroupProjectRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        group = _checked_mgr().get_group(group_id)
        if not group:
            return JSONResponse(status_code=404, content={"detail": "Group not found"})

        project_id = get_project(svc.db, body.project_name)
        if project_id is None:
            return JSONResponse(status_code=404, content={"detail": "Project not found"})

        _checked_mgr().add_group_project(group_id, project_id, body.role)
        return {"status": "ok"}

    @router.delete("/auth/groups/{group_id}/projects/{project_name}")
    def remove_group_project(group_id: int, project_name: str):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        project_id = get_project(svc.db, project_name)
        if project_id is None:
            return JSONResponse(status_code=404, content={"detail": "Project not found"})

        _checked_mgr().remove_group_project(group_id, project_id)
        return {"status": "ok"}
