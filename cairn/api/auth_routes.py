"""Authentication and user management REST endpoints (ca-124)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cairn.core.services import Services
from cairn.core.user import (
    UserManager,
    create_access_token,
    current_user,
    verify_password,
)
from cairn.core.utils import get_project


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


def register_routes(router: APIRouter, svc: Services) -> None:
    """Register auth endpoints."""
    user_mgr: UserManager | None = svc.user_manager
    config = svc.config

    def _require_auth_enabled():
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
        existing = user_mgr.get_by_username(body.username)
        if existing:
            return JSONResponse(
                status_code=409,
                content={"detail": "Username already taken"},
            )

        user = user_mgr.create_user(
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

        user = user_mgr.get_by_username(body.username)
        if not user or not verify_password(body.password, user["password_hash"]):
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

        user = user_mgr.get_by_id(ctx.user_id)
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
        """Public endpoint: is auth enabled? Are there any users yet?"""
        enabled = config.auth.enabled and bool(config.auth.jwt_secret)
        has_users = True
        if enabled and user_mgr:
            has_users = not user_mgr.is_first_user()
        return {"enabled": enabled, "has_users": has_users}

    # --- Admin endpoints ---

    @router.post("/auth/users")
    def create_user(body: CreateUserRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        existing = user_mgr.get_by_username(body.username)
        if existing:
            return JSONResponse(
                status_code=409,
                content={"detail": "Username already taken"},
            )

        user = user_mgr.create_user(
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

        return user_mgr.list_users(limit=limit, offset=offset)

    @router.patch("/auth/users/{user_id}")
    def update_user(user_id: int, body: UpdateUserRequest):
        err = _require_auth_enabled()
        if err:
            return err
        err = _require_admin()
        if err:
            return err

        result = user_mgr.update_user(
            user_id, role=body.role, is_active=body.is_active, email=body.email,
        )
        if not result:
            return JSONResponse(status_code=404, content={"detail": "User not found"})
        return result

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
            members = user_mgr.list_project_members(project_id)
            is_owner = any(
                m["user_id"] == ctx.user_id and m["project_role"] == "owner"
                for m in members
            )
            if not is_owner:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Only project owners or admins can add members"},
                )

        user_mgr.add_project_member(body.user_id, project_id, body.role)
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
            members = user_mgr.list_project_members(project_id)
            is_owner = any(
                m["user_id"] == ctx.user_id and m["project_role"] == "owner"
                for m in members
            )
            if not is_owner:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Only project owners or admins can remove members"},
                )

        user_mgr.remove_project_member(member_user_id, project_id)
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

        return user_mgr.list_project_members(project_id)
