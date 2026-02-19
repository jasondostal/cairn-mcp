"""Cairn REST API — endpoints for the web UI and content ingestion.

Split into domain modules under cairn/api/. Each module exports a
register_routes(router, svc) function that adds its endpoints.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from cairn import __version__
from cairn.api.utils import APIKeyAuthMiddleware
from cairn.core.services import Services

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

    if config.auth.enabled and config.auth.api_key:
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_key=config.auth.api_key,
            header_name=config.auth.header_name,
        )
        logger.info("API key auth enabled (header: %s)", config.auth.header_name)

    router = APIRouter()

    # Register all route modules
    from cairn.api.core import register_routes as reg_core
    from cairn.api.search import register_routes as reg_search
    from cairn.api.knowledge import register_routes as reg_knowledge
    from cairn.api.tasks import register_routes as reg_tasks
    from cairn.api.messages import register_routes as reg_messages
    from cairn.api.thinking import register_routes as reg_thinking
    from cairn.api.deprecated import register_routes as reg_deprecated
    from cairn.api.events import register_routes as reg_events
    from cairn.api.ingest import register_routes as reg_ingest
    from cairn.api.sessions import register_routes as reg_sessions
    from cairn.api.analytics import register_routes as reg_analytics
    from cairn.api.chat import register_routes as reg_chat
    from cairn.api.conversations import register_routes as reg_conversations
    from cairn.api.terminal import register_routes as reg_terminal
    from cairn.api.workspace import register_routes as reg_workspace
    from cairn.api.export import register_routes as reg_export
    from cairn.api.work_items import register_routes as reg_work_items

    reg_core(router, svc)
    reg_search(router, svc)
    reg_knowledge(router, svc)
    reg_tasks(router, svc)
    reg_messages(router, svc)
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

    app.include_router(router)
    return app
