"""Shared utilities for API route modules."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


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
