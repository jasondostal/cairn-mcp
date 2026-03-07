"""Cairn REST API — endpoints for the web UI and content ingestion.

Split into domain modules under cairn/api/. Each module exports a
register_routes(router, svc) function that adds its endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from cairn import __version__
from cairn.api.utils import APIKeyAuthMiddleware, JWTAuthMiddleware
from cairn.core.services import Services
from cairn.core.trace import clear_trace, new_trace


class TraceMiddleware(BaseHTTPMiddleware):
    """Set trace context for every REST API request."""

    async def dispatch(self, request: Request, call_next):
        entry_point = request.url.path.rstrip("/")
        new_trace(actor="rest", entry_point=entry_point)
        try:
            response = await call_next(request)
            return response
        finally:
            clear_trace()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Cache-Control for API responses (don't cache sensitive data)
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

logger = logging.getLogger(__name__)


def create_api(svc: Services) -> FastAPI:
    """Build the REST API as a FastAPI app.

    Designed to be mounted as a sub-app on the MCP Starlette parent.
    No lifespan needed — the parent handles DB lifecycle.
    """
    db = svc.db
    config = svc.config

    def _release_db_conn():
        """Safety net: release DB connection after each API request.

        Primary cleanup is in @track_operation (service layer). This catches
        any connection leaked by code outside the decorated service methods
        (e.g. middleware, auth checks, direct DB queries in endpoints).
        """
        yield
        db.release_if_held()

    app = FastAPI(
        title="Cairn API",
        version=__version__,
        description="REST API for the Cairn web UI and content ingestion.",
        docs_url="/swagger",
        redoc_url=None,
        dependencies=[Depends(_release_db_conn)],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    app.add_middleware(TraceMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Auth middleware: JWT takes priority, API key as fallback
    if config.auth.enabled and config.auth.jwt_secret and svc.user_manager:
        app.add_middleware(
            JWTAuthMiddleware,
            jwt_secret=config.auth.jwt_secret,
            user_manager=svc.user_manager,
            api_key=config.auth.api_key,
            api_key_header=config.auth.header_name,
            auth_proxy_header=config.auth.auth_proxy_header,
            trusted_proxy_ips=config.auth.trusted_proxy_ips,
        )
        logger.info("JWT auth enabled (with API key fallback)")
    elif config.auth.enabled and config.auth.api_key:
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_key=config.auth.api_key,
            header_name=config.auth.header_name,
        )
        logger.info("API key auth enabled (header: %s)", config.auth.header_name)

    router = APIRouter()

    # Register all route modules
    from cairn.api.agents import register_routes as reg_agents
    from cairn.api.alerting import register_routes as reg_alerting
    from cairn.api.analytics import register_routes as reg_analytics
    from cairn.api.audit import register_routes as reg_audit
    from cairn.api.auth_routes import register_routes as reg_auth
    from cairn.api.beliefs import register_routes as reg_beliefs
    from cairn.api.chat import register_routes as reg_chat
    from cairn.api.code import register_routes as reg_code
    from cairn.api.conversations import register_routes as reg_conversations
    from cairn.api.core import register_routes as reg_core
    from cairn.api.deliverables import register_routes as reg_deliverables
    from cairn.api.deprecated import register_routes as reg_deprecated
    from cairn.api.dispatch import register_routes as reg_dispatch
    from cairn.api.events import register_routes as reg_events
    from cairn.api.export import register_routes as reg_export
    from cairn.api.graph_edit import register_routes as reg_graph_edit
    from cairn.api.ingest import register_routes as reg_ingest
    from cairn.api.knowledge import register_routes as reg_knowledge
    from cairn.api.retention import register_routes as reg_retention
    from cairn.api.search import register_routes as reg_search
    from cairn.api.sessions import register_routes as reg_sessions
    from cairn.api.subscriptions import register_routes as reg_subscriptions
    from cairn.api.tasks import register_routes as reg_tasks
    from cairn.api.terminal import register_routes as reg_terminal
    from cairn.api.thinking import register_routes as reg_thinking
    from cairn.api.webhooks import register_routes as reg_webhooks
    from cairn.api.work_items import register_routes as reg_work_items
    from cairn.api.working_memory import register_routes as reg_working_memory
    from cairn.api.workspace import register_routes as reg_workspace

    reg_core(router, svc)
    reg_search(router, svc)
    reg_knowledge(router, svc)
    reg_tasks(router, svc)
    reg_thinking(router, svc)
    reg_deprecated(router, svc)
    reg_events(router, svc)
    reg_ingest(router, svc)
    reg_sessions(router, svc)
    reg_analytics(router, svc)
    reg_chat(router, svc)
    reg_conversations(router, svc)
    reg_terminal(router, svc, app=app)
    reg_workspace(router, svc)
    reg_export(router, svc)
    reg_work_items(router, svc)
    reg_code(router, svc)
    reg_dispatch(router, svc)
    reg_graph_edit(router, svc)
    reg_audit(router, svc)
    reg_webhooks(router, svc)
    reg_alerting(router, svc)
    reg_retention(router, svc)
    reg_deliverables(router, svc)
    reg_subscriptions(router, svc)
    reg_agents(router, svc)
    reg_auth(router, svc)
    reg_working_memory(router, svc)
    reg_beliefs(router, svc)

    app.include_router(router)
    return app
