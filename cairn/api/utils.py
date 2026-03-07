"""Shared utilities for API route modules."""

from __future__ import annotations

import hmac
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def require_admin() -> JSONResponse | None:
    """Check that the current user has admin role. Returns 403 response or None."""
    from cairn.core.user import current_user
    ctx = current_user()
    if not ctx or ctx.role != "admin":
        return JSONResponse(
            status_code=403,
            content={"detail": "Admin access required"},
        )
    return None


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
        if path in _JWT_OPEN_PATHS:
            return await call_next(request)

        token = request.headers.get(self.header_name)
        if not token or not hmac.compare_digest(token, self.api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)


# Paths that bypass JWT auth (public endpoints).
# The REST API is mounted at /api, so middleware sees mount-relative paths
# (e.g. /auth/status, not /api/auth/status). Include both for safety.
_JWT_OPEN_PATHS = frozenset({
    "/status", "/swagger", "/openapi.json",
    "/api/status", "/api/swagger", "/api/openapi.json",
    "/auth/login", "/auth/register", "/auth/status",
    "/auth/oidc/login", "/auth/oidc/callback", "/auth/oidc/exchange",
    "/api/auth/login", "/api/auth/register", "/api/auth/status",
    "/api/auth/oidc/login", "/api/auth/oidc/callback", "/api/auth/oidc/exchange",
})


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT Bearer token authentication middleware.

    Decodes JWT from Authorization header, loads UserContext, and sets
    the contextvar for the request duration. Falls back to API key auth
    if an X-API-Key header is present instead. Supports trusted reverse
    proxy header authentication.
    """

    def __init__(self, app, *, jwt_secret: str, user_manager, api_key: str | None = None, api_key_header: str = "X-API-Key",
                 auth_proxy_header: str = "", trusted_proxy_ips: str = ""):
        super().__init__(app)
        self.jwt_secret = jwt_secret
        self.user_manager = user_manager
        self.api_key = api_key
        self.api_key_header = api_key_header
        self.auth_proxy_header = auth_proxy_header
        self.trusted_proxy_ips = trusted_proxy_ips

    async def dispatch(self, request: Request, call_next):
        from cairn.core.auth import is_trusted_proxy, resolve_bearer_token
        from cairn.core.user import clear_user, set_user

        # Always allow CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow open paths
        path = request.url.path.rstrip("/")
        if path in _JWT_OPEN_PATHS:
            return await call_next(request)

        try:
            # Check trusted reverse proxy header first
            if self.auth_proxy_header:
                header_value = request.headers.get(self.auth_proxy_header)
                if header_value:
                    client_ip = request.client.host if request.client else ""
                    if self.trusted_proxy_ips:
                        if is_trusted_proxy(client_ip, self.trusted_proxy_ips):
                            ctx = self.user_manager.load_user_context_by_username(header_value)
                            if ctx:
                                set_user(ctx)
                            return await call_next(request)
                        logger.debug(
                            "Proxy header '%s' ignored — source %s not in TRUSTED_PROXY_IPS",
                            self.auth_proxy_header, client_ip,
                        )
                    else:
                        # No trusted IPs configured — reject (fail closed)
                        logger.warning(
                            "Proxy header '%s' present but TRUSTED_PROXY_IPS not configured — "
                            "ignoring header. Set CAIRN_TRUSTED_PROXY_IPS to enable proxy auth.",
                            self.auth_proxy_header,
                        )

            # Check for API key (legacy/simple auth)
            if self.api_key:
                api_key_value = request.headers.get(self.api_key_header)
                if api_key_value and hmac.compare_digest(api_key_value, self.api_key):
                    return await call_next(request)

            # Check for Bearer token (JWT or PAT)
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid authorization"},
                )

            token = auth_header[7:]
            ctx = resolve_bearer_token(
                token,
                jwt_secret=self.jwt_secret,
                user_manager=self.user_manager,
            )
            if ctx is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
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
