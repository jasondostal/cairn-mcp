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
from cairn.core.services import create_services
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

# Module-level globals — populated by lifespan before MCP tools execute.
# Declared here so tool functions can reference them; assigned in _init_services().
_svc = None
config = _base_config  # updated in lifespan
db = None
graph_provider = None
memory_store = None
search_engine = None
cluster_engine = None
project_manager = None
task_manager = None
thinking_engine = None
session_synthesizer = None
consolidation_engine = None
event_bus = None
event_dispatcher = None
drift_detector = None

work_item_manager = None
deliverable_manager = None

# Resource locking — in-memory singleton (ca-156)
from cairn.core.resource_lock import ResourceLockManager

_lock_manager = ResourceLockManager()
analytics_tracker = None
rollup_worker = None
workspace_manager = None
ingest_pipeline = None
belief_store = None


def _init_services(svc):
    """Assign module globals from a Services instance."""
    global _svc, config, db, graph_provider, memory_store, search_engine
    global cluster_engine, project_manager, task_manager
    global thinking_engine, session_synthesizer, consolidation_engine
    global event_bus, event_dispatcher, drift_detector
    global work_item_manager, deliverable_manager
    global analytics_tracker, rollup_worker, workspace_manager
    global ingest_pipeline, belief_store

    _svc = svc
    config = svc.config
    db = svc.db
    graph_provider = svc.graph_provider
    memory_store = svc.memory_store
    search_engine = svc.search_engine
    cluster_engine = svc.cluster_engine
    project_manager = svc.project_manager
    task_manager = svc.task_manager
    work_item_manager = svc.work_item_manager
    deliverable_manager = svc.deliverable_manager
    thinking_engine = svc.thinking_engine
    session_synthesizer = svc.session_synthesizer
    consolidation_engine = svc.consolidation_engine
    event_bus = svc.event_bus
    event_dispatcher = svc.event_dispatcher
    drift_detector = svc.drift_detector
    analytics_tracker = svc.analytics_tracker
    rollup_worker = svc.rollup_worker
    workspace_manager = svc.workspace_manager
    ingest_pipeline = svc.ingest_pipeline
    belief_store = svc.belief_store

    # Startup assertion: critical services must be non-None (ca-211)
    _critical = {"db": db, "config": config, "memory_store": memory_store,
                 "search_engine": search_engine, "work_item_manager": work_item_manager,
                 "task_manager": task_manager}
    _missing = [k for k, v in _critical.items() if v is None]
    if _missing:
        logger.error("FATAL: critical services are None after init: %s", _missing)
        raise RuntimeError(f"Service initialization failed: {', '.join(_missing)} are None")


async def _in_thread(fn, *args, timeout: float = 120.0, **kwargs):
    """Run fn in a thread pool, then release the DB connection back to the pool.

    The Database class uses threading.local() to hold connections per-thread.
    With asyncio.to_thread(), worker threads from the ThreadPoolExecutor
    check out connections but never return them — causing pool exhaustion
    and deadlock after enough concurrent calls. This wrapper ensures every
    thread returns its connection when the work is done.

    A timeout (default 120s) prevents hung operations from blocking forever.
    The DB connection is released even on timeout (via the finally block in
    _wrapped — the thread still runs to completion and hits finally).
    """
    def _wrapped():
        try:
            return fn(*args, **kwargs)
        finally:
            if db is not None:
                db._release()
    try:
        return await asyncio.wait_for(asyncio.to_thread(_wrapped), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("Tool operation timed out after %.0fs", timeout)
        raise


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
    """Start background workers and optional graph connection."""
    db_instance.reconcile_vector_dimensions(cfg.embedding.dimensions)
    if svc.graph_provider:
        try:
            svc.graph_provider.connect()
            svc.graph_provider.ensure_schema()
            logger.info("Neo4j graph connected and schema ensured")
            # Reconcile PG vs Neo4j state (PG wins)
            try:
                from cairn.core.reconciliation import reconcile_graph
                reconcile_graph(db_instance, svc.graph_provider)
            except Exception:
                logger.warning("Graph reconciliation failed", exc_info=True)
        except Exception:
            logger.warning("Neo4j connection failed — graph features disabled", exc_info=True)
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
    if svc.graph_provider:
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
# Register MCP tools from domain modules
# ============================================================

def _server_globals():
    """Build a globals dict for tool modules that reads live module state."""
    import cairn.server as _self
    return _ServerGlobals(_self)


class _ServerGlobals:
    """Proxy dict that reads live module-level globals from server.py."""

    def __init__(self, module):
        self._mod = module

    def __getitem__(self, key):
        try:
            return getattr(self._mod, key)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key, default=None):
        return getattr(self._mod, key, default)


from cairn.tools import register_all  # noqa: E402

register_all(mcp, _server_globals())


# ============================================================
# Entry point
# ============================================================

def main():
    """Run the Cairn MCP server."""
    if _base_config.transport == "http":
        import uvicorn

        from cairn.api import create_api

        # Get MCP's Starlette app (parent — owns lifespan, serves /mcp)
        mcp_app = mcp.streamable_http_app()

        # Wrap MCP's lifespan with DB lifecycle.
        # streamable_http_app() only starts the session manager — our custom
        # lifespan (DB connect) doesn't fire unless we inject it here.
        _mcp_lifespan = mcp_app.router.lifespan_context

        # Pre-connect DB and build services so we can mount API before app starts
        db_instance = Database(_base_config.db)
        db_instance.connect()
        db_instance.run_migrations()

        final_config = _build_config_with_overrides(db_instance)
        svc = create_services(config=final_config, db=db_instance)
        _init_services(svc)

        # Mount REST API and auth middleware before app starts
        api = create_api(svc)
        mcp_app.mount("/api", api)

        # MCP HTTP: enforce auth on /mcp/* when auth is enabled (ca-162)
        if final_config.auth.enabled and final_config.auth.jwt_secret and svc.user_manager:
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
            logger.info("MCP HTTP auth enforcement enabled")

        # Security: warn about default database passwords
        if final_config.db.password == "cairn-dev-password":
            logger.warning(
                "SECURITY: Using default database password 'cairn-dev-password'. "
                "Set CAIRN_DB_PASS to a strong password for production deployments."
            )
        if final_config.neo4j.password == "cairn-dev-password" and final_config.capabilities.code_intelligence:
            logger.warning(
                "SECURITY: Using default Neo4j password 'cairn-dev-password'. "
                "Set CAIRN_NEO4J_PASSWORD to a strong password for production deployments."
            )

        # Security: warn if proxy auth header is configured without source IP restriction
        if final_config.auth.auth_proxy_header and not final_config.auth.trusted_proxy_ips:
            logger.warning(
                "SECURITY: CAIRN_AUTH_PROXY_HEADER='%s' is set without CAIRN_TRUSTED_PROXY_IPS. "
                "Any client can forge this header and bypass authentication. "
                "Set CAIRN_TRUSTED_PROXY_IPS to the IP or CIDR of your reverse proxy (e.g. 172.20.0.2).",
                final_config.auth.auth_proxy_header,
            )

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
