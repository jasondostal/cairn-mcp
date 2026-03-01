"""Shared utilities for API route modules."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def parse_multi(param: str | None) -> list[str] | None:
    """Split a comma-separated query param into a list, or None if empty."""
    if not param:
        return None
    parts = [p.strip() for p in param.split(",") if p.strip()]
    return parts if parts else None


def _llm_model_name(config) -> str:
    """Return the active LLM model name based on backend."""
    backend = config.llm.backend
    if backend == "ollama":
        return config.llm.ollama_model
    if backend == "bedrock":
        return config.llm.bedrock_model
    if backend == "gemini":
        return config.llm.gemini_model
    if backend == "openai":
        return config.llm.openai_model
    return backend


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication middleware.

    When enabled, checks for a valid API key in the configured header.
    Allows OPTIONS requests (CORS preflight) and health/swagger endpoints through.
    """

    def __init__(self, app, api_key: str, header_name: str = "X-API-Key"):
        super().__init__(app)
        self.api_key = api_key
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight, health, and docs
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path.rstrip("/")
        if path in ("/status", "/swagger", "/openapi.json",
                     "/api/status", "/api/swagger", "/api/openapi.json"):
            return await call_next(request)

        token = request.headers.get(self.header_name)
        if not token or token != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)


# Paths that bypass JWT auth (public endpoints)
_JWT_OPEN_PATHS = frozenset({
    "/status", "/swagger", "/openapi.json",
    "/api/status", "/api/swagger", "/api/openapi.json",
    "/api/auth/login", "/api/auth/register", "/api/auth/status",
})


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT Bearer token authentication middleware.

    Decodes JWT from Authorization header, loads UserContext, and sets
    the contextvar for the request duration. Falls back to API key auth
    if an X-API-Key header is present instead.
    """

    def __init__(self, app, *, jwt_secret: str, user_manager, api_key: str | None = None, api_key_header: str = "X-API-Key"):
        super().__init__(app)
        self.jwt_secret = jwt_secret
        self.user_manager = user_manager
        self.api_key = api_key
        self.api_key_header = api_key_header

    async def dispatch(self, request: Request, call_next):
        from cairn.core.user import clear_user, decode_access_token, set_user

        # Always allow CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow open paths
        path = request.url.path.rstrip("/")
        if path in _JWT_OPEN_PATHS:
            return await call_next(request)

        try:
            # Check for API key first (MCP HTTP clients use this)
            if self.api_key:
                api_key_value = request.headers.get(self.api_key_header)
                if api_key_value and api_key_value == self.api_key:
                    return await call_next(request)

            # Check for Bearer token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid authorization"},
                )

            token = auth_header[7:]  # Strip "Bearer "
            payload = decode_access_token(token, secret=self.jwt_secret)
            if payload is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )

            user_id = int(payload["sub"])
            ctx = self.user_manager.load_user_context(user_id)
            if ctx is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "User not found or deactivated"},
                )

            set_user(ctx)
            try:
                return await call_next(request)
            finally:
                clear_user()

        except Exception:
            logger.warning("JWT auth middleware error", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Authentication error"},
            )
