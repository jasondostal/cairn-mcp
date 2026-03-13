"""Cairn MCP Server. Entry point for the semantic memory system."""

import asyncio
import concurrent.futures
import logging
import sys
from contextlib import asynccontextmanager

# Fix __main__ module identity: when run via `python -m cairn.server`, the module
# is only registered as __main__. Any `import cairn.server` elsewhere creates a
# second copy with stale None globals. Register ourselves so the proxy reads the
# same module instance that _init_services() writes to.
if __name__ == "__main__" and "cairn.server" not in sys.modules:
    sys.modules["cairn.server"] = sys.modules["__main__"]

from mcp.server.fastmcp import FastMCP

from cairn.config import apply_overrides, load_config
from cairn.core.services import Services, create_services
from cairn.storage import settings_store
from cairn.storage.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cairn")

# Base config from env vars only (loaded at module import time).
# DB overrides are applied during lifespan once the database is connected.
_base_config = load_config()

# Module-level state — only what lifespan/main genuinely need.
# Tools no longer access these; they receive the Services dataclass directly.
_svc: Services | None = None


def _validate_config(config) -> None:
    """Startup config validation — fail-loud on insecure defaults (ca-247).

    Set CAIRN_ALLOW_INSECURE=true to bypass in local dev environments.
    """
    import os
    allow_insecure = os.getenv("CAIRN_ALLOW_INSECURE", "").lower() in ("true", "1", "yes")
    errors: list[str] = []

    # Default passwords
    if config.db.password == "cairn-dev-password":
        if allow_insecure:
            logger.warning("SECURITY: Using default DB password (allowed by CAIRN_ALLOW_INSECURE)")
        else:
            errors.append(
                "CAIRN_DB_PASS is the default 'cairn-dev-password'. "
                "Set a strong password or export CAIRN_ALLOW_INSECURE=true for local dev."
            )

    if config.neo4j.password == "cairn-dev-password":
        if allow_insecure:
            logger.warning("SECURITY: Using default Neo4j password (allowed by CAIRN_ALLOW_INSECURE)")
        else:
            errors.append(
                "CAIRN_NEO4J_PASSWORD is the default 'cairn-dev-password'. "
                "Set a strong password or export CAIRN_ALLOW_INSECURE=true for local dev."
            )

    # Auth enabled without credentials
    if config.auth.enabled:
        if not config.auth.jwt_secret and not config.auth.api_key:
            errors.append(
                "CAIRN_AUTH_ENABLED=true but neither CAIRN_AUTH_JWT_SECRET nor CAIRN_API_KEY is set. "
                "API would be unauthenticated."
            )

    # Proxy auth without IP restriction
    if config.auth.auth_proxy_header and not config.auth.trusted_proxy_ips:
        errors.append(
            f"CAIRN_AUTH_PROXY_HEADER='{config.auth.auth_proxy_header}' is set without "
            "CAIRN_TRUSTED_PROXY_IPS. Any client can forge this header."
        )

    if errors:
        for e in errors:
            logger.error("CONFIG: %s", e)
        raise RuntimeError(
            f"Startup blocked by {len(errors)} config error(s). "
            "Fix the issues above or set CAIRN_ALLOW_INSECURE=true for local dev."
        )


def _init_services(svc: Services):
    """Store the Services instance and validate critical fields."""
    global _svc
    _svc = svc

    # Startup assertion: critical services must be non-None (ca-211)
    _critical = {"db": svc.db, "config": svc.config, "memory_store": svc.memory_store,
                 "search_engine": svc.search_engine, "work_item_manager": svc.work_item_manager}
    _missing = [k for k, v in _critical.items() if v is None]
    if _missing:
        logger.error("FATAL: critical services are None after init: %s", _missing)
        raise RuntimeError(f"Service initialization failed: {', '.join(_missing)} are None")


def _build_config_with_overrides(db_instance):
    """Load DB overrides and rebuild config."""
    try:
        overrides = settings_store.load_all(db_instance)
    except Exception:
        logger.warning("Failed to load settings overrides, using base config", exc_info=True)
        overrides = {}
    if overrides:
        logger.info("Loaded %d setting overrides from DB", len(overrides))
        return apply_overrides(_base_config, overrides)
    return _base_config


def _start_workers(svc, cfg, db_instance):
    """Start background workers and graph connection."""
    db_instance.reconcile_vector_dimensions(cfg.embedding.dimensions)
    svc.graph_provider.connect()
    svc.graph_provider.ensure_schema()
    logger.info("Neo4j graph connected and schema ensured")
    try:
        from cairn.core.reconciliation import reconcile_graph
        reconcile_graph(db_instance, svc.graph_provider)
    except Exception:
        logger.warning("Graph reconciliation failed", exc_info=True)
    if svc.event_dispatcher:
        svc.event_dispatcher.start()
    if svc.analytics_tracker:
        svc.analytics_tracker.start()
    if svc.rollup_worker:
        svc.rollup_worker.start()
    if svc.decay_worker:
        svc.decay_worker.start()
    if svc.consolidation_worker:
        svc.consolidation_worker.start()
    if svc.webhook_worker:
        svc.webhook_worker.start()
    if svc.alert_worker:
        svc.alert_worker.start()
    if svc.retention_worker:
        svc.retention_worker.start()
    logger.info("Cairn started. Embedding: %s (%d-dim)", cfg.embedding.backend, cfg.embedding.dimensions)


def _stop_workers(svc, db_instance):
    """Stop background workers and close connections."""
    if svc.event_dispatcher:
        svc.event_dispatcher.stop()
    if svc.rollup_worker:
        svc.rollup_worker.stop()
    if svc.decay_worker:
        svc.decay_worker.stop()
    if svc.consolidation_worker:
        svc.consolidation_worker.stop()
    if svc.webhook_worker:
        svc.webhook_worker.stop()
    if svc.alert_worker:
        svc.alert_worker.stop()
    if svc.retention_worker:
        svc.retention_worker.stop()
    from cairn.core import otel
    otel.shutdown()
    if svc.analytics_tracker:
        svc.analytics_tracker.stop()
    try:
        svc.graph_provider.close()
    except Exception:
        pass
    db_instance.close()
    logger.info("Cairn stopped.")


# ============================================================
# Lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Connect to database, load overrides, create services, and run lifecycle.

    In HTTP mode, main() handles DB/services/workers before uvicorn starts,
    so this lifespan only runs the MCP session manager (via FastMCP internals).
    The actual DB lifecycle is managed by combined_lifespan in main().
    """
    if _base_config.transport == "http":
        # HTTP mode: main() already created the DB pool, services, and workers.
        # Yielding here just lets the MCP session manager do its thing.
        yield {}
        return

    # Stdio mode: full lifecycle
    db_instance = Database(_base_config.db)
    db_instance.connect()
    db_instance.run_migrations()

    final_config = _build_config_with_overrides(db_instance)
    svc = create_services(config=final_config, db=db_instance)
    _init_services(svc)

    # Register MCP tools now that Services is available (ca-237)
    from cairn.tools import register_all
    register_all(mcp, svc)

    # Stdio identity mapping: set UserContext for the session lifetime (ca-162)
    if final_config.auth.enabled and final_config.auth.stdio_user and svc.user_manager:
        from cairn.core.user import set_user
        stdio_user = svc.user_manager.get_by_username(final_config.auth.stdio_user)
        if stdio_user and stdio_user.get("is_active"):
            ctx = svc.user_manager.load_user_context(stdio_user["id"])
            if ctx:
                set_user(ctx)
                logger.info("Stdio identity set: %s (role=%s)", ctx.username, ctx.role)
        else:
            logger.warning("CAIRN_STDIO_USER=%s not found or inactive", final_config.auth.stdio_user)

    _start_workers(svc, final_config, db_instance)
    try:
        yield {}
    finally:
        _stop_workers(svc, db_instance)


# Create MCP server
mcp_kwargs = dict(
    name="cairn",
    instructions=(
        "Semantic memory for AI agents. Store, search, and discover patterns across persistent context.\n"
        "\n"
        "CRITICAL BEHAVIOR — SEARCH BEFORE GUESSING:\n"
        "When you hit an 'I don't know' moment — a hostname, file path, deploy command, architecture detail, "
        "workflow, or any infrastructure/process question — SEARCH THIS MEMORY FIRST. Do not guess. Do not "
        "ask the user. Do not SSH somewhere and hope. The answer is almost certainly already stored. One search. "
        "That's all it takes.\n"
        "\n"
        "SESSION STARTUP SEQUENCE:\n"
        "Preferred: orient(project) — single call returning rules, trail, learnings, and work items.\n"
        "Granular fallback: rules() + search(query='learning') + work_items(action='list') individually.\n"
        "Then summarize the landscape and ask what we're working on.\n"
        "\n"
        "ONGOING USE — Memory is not just for boot:\n"
        "The startup sequence loads broad context. But mid-task questions ('how do we deploy?', "
        "'where is the config?', 'what port does X use?') require NEW searches. Do not assume the "
        "boot context covers everything. Search is cheap. Being wrong is expensive.\n"
        "\n"
        "PROGRESSIVE DISCLOSURE: search (summaries) → recall (full content). "
        "Search first, recall specific IDs when you need details.\n"
        "\n"
        "STORE THOUGHTFULLY: Ask — would losing this diminish a future session? "
        "If yes, store it. Consolidate when possible, but don't let consolidation prevent you "
        "from capturing high-signal moments (relationship milestones, key realizations, trust "
        "events, paradigm shifts) just because a task isn't 'done' yet.\n"
        "\n"
        "BACKGROUND WORK — DISPATCH, DON'T SUBAGENT:\n"
        "When you need to background a task, use dispatch() instead of native subagents. "
        "dispatch() creates a tracked workspace session with a structured briefing — all in one call. "
        "The job becomes visible in cairn-ui, heartbeats progress, supports gates for human input, "
        "and survives session drops. Native subagents are invisible to cairn and vanish if the session dies."
    ),
    lifespan=lifespan,
)
if _base_config.transport == "http":
    mcp_kwargs["host"] = _base_config.http_host
    mcp_kwargs["port"] = _base_config.http_port

mcp = FastMCP(**mcp_kwargs)  # type: ignore[arg-type]


# ============================================================
# Entry point
# ============================================================

def _mcp_oauth_enabled(config) -> bool:
    """Check if MCP OAuth2 Authorization Server should be enabled."""
    return (
        config.auth.mcp_oauth.enabled
        and config.auth.enabled
        and config.auth.oidc.enabled
        and bool(config.auth.jwt_secret)
        and bool(config.public_url)
    )


def main():
    """Run the Cairn MCP server."""
    if _base_config.transport == "http":
        import uvicorn

        from cairn.api import create_api

        # Inject our resilient session manager BEFORE streamable_http_app()
        # creates the default one. The SDK checks `if self._session_manager is None`
        # and skips creation if it's already set, so our instance gets used
        # throughout the ASGI app.
        #
        # Why: The SDK's StreamableHTTPSessionManager stores sessions in an
        # in-memory dict. Container restart = all session IDs gone = clients
        # get hard 404s. Our ResilientSessionManager auto-recreates sessions
        # on unknown IDs instead of 404'ing. All application state lives in
        # PostgreSQL — transport sessions are disposable (12-factor).
        from cairn.session import ResilientSessionManager
        mcp._session_manager = ResilientSessionManager(
            app=mcp._mcp_server,
            event_store=mcp._event_store,
            json_response=mcp.settings.json_response,
            stateless=mcp.settings.stateless_http,
            security_settings=mcp.settings.transport_security,
            retry_interval=mcp._retry_interval,
        )

        # --- DB + services init (before streamable_http_app for OAuth2 injection) ---
        db_instance = Database(_base_config.db)
        db_instance.connect()
        db_instance.run_migrations()

        final_config = _build_config_with_overrides(db_instance)
        svc = create_services(config=final_config, db=db_instance)
        _init_services(svc)

        # Register MCP tools now that Services is available (ca-237)
        from cairn.tools import register_all
        register_all(mcp, svc)

        # --- MCP OAuth2 Authorization Server (for Claude.ai remote access) ---
        _oauth_provider = None
        if _mcp_oauth_enabled(final_config) and svc.user_manager:
            from mcp.server.auth.provider import ProviderTokenVerifier
            from mcp.server.auth.settings import (
                AuthSettings,
                ClientRegistrationOptions,
                RevocationOptions,
            )

            from cairn.core.oauth2_server import CairnOAuthProvider

            _oauth_provider = CairnOAuthProvider(
                db=db_instance,
                oidc_config=final_config.auth.oidc,
                auth_config=final_config.auth,
                mcp_oauth_config=final_config.auth.mcp_oauth,
                public_url=final_config.public_url,
                user_manager=svc.user_manager,
            )

            # Inject auth settings and provider onto FastMCP before building the app.
            # The SDK's streamable_http_app() reads these to create OAuth2 routes
            # and bearer auth middleware automatically.
            mcp.settings.auth = AuthSettings(
                issuer_url=final_config.public_url,
                resource_server_url=f"{final_config.public_url.rstrip('/')}/mcp",
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    valid_scopes=["mcp:tools"],
                    default_scopes=["mcp:tools"],
                ),
                revocation_options=RevocationOptions(enabled=True),
            )
            mcp._auth_server_provider = _oauth_provider
            mcp._token_verifier = ProviderTokenVerifier(_oauth_provider)
            logger.info("MCP OAuth2 Authorization Server enabled (issuer: %s)", final_config.public_url)

        # Get MCP's Starlette app (parent — owns lifespan, serves /mcp)
        # NOTE: must be called AFTER OAuth2 injection so SDK creates auth routes
        mcp_app = mcp.streamable_http_app()

        # Add /oauth/callback route for Authentik redirect (not handled by SDK)
        if _oauth_provider:
            from starlette.routing import Route
            mcp_app.routes.insert(0, Route(
                "/oauth/callback",
                endpoint=_oauth_provider.callback_handler,
                methods=["GET"],
            ))

        # Wrap MCP's lifespan with DB lifecycle.
        _mcp_lifespan = mcp_app.router.lifespan_context

        # Mount REST API
        api = create_api(svc)
        mcp_app.mount("/api", api)

        # MCP HTTP auth: when OAuth2 is enabled, the SDK's built-in
        # RequireAuthMiddleware + BearerAuthBackend handle /mcp auth.
        # The CairnOAuthProvider.load_access_token() bridges to UserContext.
        # When OAuth2 is disabled, use the legacy MCPAuthMiddleware.
        if not _oauth_provider and final_config.auth.enabled and final_config.auth.jwt_secret and svc.user_manager:
            from fastapi.responses import JSONResponse
            from starlette.middleware.base import BaseHTTPMiddleware

            from cairn.core.auth import is_trusted_proxy, resolve_bearer_token
            from cairn.core.user import clear_user, set_user

            _mcp_jwt_secret = final_config.auth.jwt_secret
            _mcp_user_manager = svc.user_manager
            _mcp_api_key = final_config.auth.api_key
            _mcp_api_key_header = final_config.auth.header_name
            _mcp_proxy_header = final_config.auth.auth_proxy_header
            _mcp_trusted_ips = final_config.auth.trusted_proxy_ips

            class MCPAuthMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    # Only apply to MCP endpoints
                    if not request.url.path.startswith("/mcp"):
                        return await call_next(request)
                    # Allow CORS preflight and OAuth discovery probes
                    if request.method == "OPTIONS":
                        return await call_next(request)
                    if "/.well-known/" in request.url.path:
                        return await call_next(request)

                    # Trusted reverse proxy header
                    if _mcp_proxy_header:
                        header_value = request.headers.get(_mcp_proxy_header)
                        if header_value:
                            client_ip = request.client.host if request.client else ""
                            if _mcp_trusted_ips:
                                if is_trusted_proxy(client_ip, _mcp_trusted_ips):
                                    if _mcp_user_manager:
                                        ctx = _mcp_user_manager.load_user_context_by_username(header_value)
                                        if ctx:
                                            set_user(ctx)
                                    return await call_next(request)
                                logger.debug(
                                    "MCP: proxy header '%s' ignored — source %s not in TRUSTED_PROXY_IPS",
                                    _mcp_proxy_header, client_ip,
                                )
                            else:
                                # No trusted IPs configured — reject (fail closed)
                                logger.warning(
                                    "MCP: proxy header '%s' present but TRUSTED_PROXY_IPS not configured — ignoring",
                                    _mcp_proxy_header,
                                )

                    # Try API key fallback (legacy/simple auth)
                    if _mcp_api_key:
                        import hmac as _hmac
                        key = request.headers.get(_mcp_api_key_header)
                        if key and _hmac.compare_digest(key, _mcp_api_key):
                            return await call_next(request)

                    # Try Bearer token (JWT or PAT) via unified resolution
                    auth_header = request.headers.get("Authorization", "")
                    if auth_header.startswith("Bearer "):
                        token = auth_header[7:]
                        ctx = resolve_bearer_token(
                            token,
                            jwt_secret=_mcp_jwt_secret,
                            user_manager=_mcp_user_manager,
                        )
                        if ctx:
                            set_user(ctx)
                            try:
                                return await call_next(request)
                            finally:
                                clear_user()

                    # Auth enabled but no valid credentials — reject
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required"},
                    )

            mcp_app.add_middleware(MCPAuthMiddleware)
            logger.info("MCP HTTP auth enforcement enabled (legacy middleware)")

        # --- Startup config validation (ca-247) ---
        _validate_config(final_config)

        @asynccontextmanager
        async def combined_lifespan(app):
            # Size thread pool to DB pool capacity + headroom for concurrent tool calls
            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
            loop.set_default_executor(executor)

            _start_workers(svc, final_config, db_instance)
            try:
                async with _mcp_lifespan(app) as state:
                    yield state
            finally:
                _stop_workers(svc, db_instance)
                executor.shutdown(wait=False)

        mcp_app.router.lifespan_context = combined_lifespan

        # NOTE: uvicorn workers>1 requires an import string, not an app object.
        # Multi-worker also needs DB/services init moved into the per-worker lifespan
        # (forked TCP connections are broken). Planned for 0.64.0.
        logger.info(
            "Starting Cairn (HTTP on %s:%d — MCP at /mcp, API at /api)",
            _base_config.http_host, _base_config.http_port,
        )
        # Enable uvicorn proxy headers when trusted proxies are configured
        # so request.client.host reflects the real client IP from X-Forwarded-For
        _uvicorn_kwargs: dict = {}
        if final_config.auth.trusted_proxy_ips:
            _uvicorn_kwargs["proxy_headers"] = True
            _uvicorn_kwargs["forwarded_allow_ips"] = final_config.auth.trusted_proxy_ips

        uvicorn.run(
            mcp_app,
            host=_base_config.http_host,
            port=_base_config.http_port,
            **_uvicorn_kwargs,
        )
    else:
        logger.info("Starting Cairn MCP server (stdio)")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
