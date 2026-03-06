"""Cairn MCP Server. Entry point for the semantic memory system."""

import asyncio
import concurrent.futures
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cairn.config import apply_overrides, load_config
from cairn.core.budget import apply_list_budget
from cairn.core.constants import (
    BUDGET_INSIGHTS_PER_ITEM,
    BUDGET_RECALL_PER_ITEM,
    BUDGET_RULES_PER_ITEM,
    BUDGET_SEARCH_PER_ITEM,
    MAX_CONTENT_SIZE,
    MAX_LIMIT,
    MAX_RECALL_IDS,
    VALID_MEMORY_TYPES,
    VALID_SEARCH_MODES,
    ActivityType,
    MemoryAction,
)
from cairn.core.services import create_services
from cairn.core.status import get_status
from cairn.core.utils import ValidationError, validate_search, validate_store
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
working_memory_store = None
belief_store = None


def _init_services(svc):
    """Assign module globals from a Services instance."""
    global _svc, config, db, graph_provider, memory_store, search_engine
    global cluster_engine, project_manager, task_manager
    global thinking_engine, session_synthesizer, consolidation_engine
    global event_bus, event_dispatcher, drift_detector
    global work_item_manager, deliverable_manager
    global analytics_tracker, rollup_worker, workspace_manager
    global ingest_pipeline, working_memory_store, belief_store

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
    working_memory_store = svc.working_memory_store
    belief_store = svc.belief_store


async def _in_thread(fn, *args, **kwargs):
    """Run fn in a thread pool, then release the DB connection back to the pool.

    The Database class uses threading.local() to hold connections per-thread.
    With asyncio.to_thread(), worker threads from the ThreadPoolExecutor
    check out connections but never return them — causing pool exhaustion
    and deadlock after enough concurrent calls. This wrapper ensures every
    thread returns its connection when the work is done.
    """
    def _wrapped():
        try:
            return fn(*args, **kwargs)
        finally:
            if db is not None:
                db._release()
    return await asyncio.to_thread(_wrapped)


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

mcp = FastMCP(**mcp_kwargs)


# ============================================================
# Tool 1: store
# ============================================================

@mcp.tool()
async def store(
    content: str,
    project: str,
    memory_type: str = "note",
    importance: float = 0.5,
    tags: list[str] | None = None,
    session_name: str | None = None,
    related_files: list[str] | None = None,
    related_ids: list[int] | None = None,
    file_hashes: dict[str, str] | None = None,
    author: str | None = None,
    event_at: str | None = None,
    valid_until: str | None = None,
    salience: float | None = None,
) -> dict:
    """Store a memory with automatic embedding generation and optional LLM enrichment.

    WHEN TO STORE — Ask: "Would losing this diminish a future session?"
    - Key decisions, architecture choices, learnings — the usual
    - Relationship milestones, trust events, paradigm shifts — these matter as much
      as technical decisions and only live in memory, not in git
    - Context switches — save state before moving to a different topic
    - User explicitly says "remember this", "save this", "store this"
    Consolidate when you can (one journey memory > five incremental notes),
    but never skip a high-signal moment just because the task isn't "done."

    DON'T STORE:
    - Low-signal incremental steps that won't matter next session
    - Duplicate information already stored (search first!)

    MEMORY TYPES: note, decision, rule, code-snippet, learning, research,
    discussion, progress, task, debug, design,
    hypothesis, question, tension, connection, thread, intuition.
    Use 'rule' for behavioral guardrails. Use '__global__' project for cross-project rules.
    Ephemeral types (hypothesis, question, tension, connection, thread, intuition) are
    stored with salience that decays over time. Use the working_memory tool for these
    or pass salience here directly.

    Args:
        content: The memory content. Can be plain text, markdown, or code.
        project: Project name for organization. Use '__global__' for cross-project rules.
        memory_type: Classification (see types above).
        importance: Priority score 0.0-1.0. Higher = more important. 0.9+ for critical rules/decisions.
        tags: Optional tags for categorization. Merged with auto-tags, not replaced.
        session_name: Optional session grouping (e.g., 'sprint-1', 'feature-auth').
        related_files: File paths related to this memory for code context searches.
        related_ids: IDs of related memories to link.
        file_hashes: Optional dict of {file_path: content_hash} for drift detection.
        author: Who created this memory. Use "user" for human-authored, "assistant" for
            AI-authored, or a specific name. Both voices are valid — this is for attribution,
            not filtering.
        event_at: When this event/fact occurred (ISO 8601). Distinct from created_at
            (when we learned it). Use for temporal queries like "what happened last week?"
        valid_until: When this knowledge stops being true (ISO 8601). NULL = still valid.
            Use for docs, architecture decisions, or any knowledge with a shelf life.
        salience: Ephemeral salience score (0.0-1.0). When set, memory decays over time.
            Auto-set for ephemeral types (hypothesis, question, tension, etc.) if omitted.
            NULL = crystallized (permanent) memory.
    """
    try:
        validate_store(content, project, memory_type, importance, tags, session_name)

        def _do_store():
            return memory_store.store(
                content=content,
                project=project,
                memory_type=memory_type,
                importance=importance,
                tags=tags,
                session_name=session_name,
                related_files=related_files,
                related_ids=related_ids,
                file_hashes=file_hashes,
                author=author,
                event_at=event_at,
                valid_until=valid_until,
                salience=salience,
            )

        return await _in_thread(_do_store)
    except ValidationError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("store failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 2: search
# ============================================================

@mcp.tool()
async def search(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    search_mode: str = "semantic",
    limit: int = 10,
    include_full: bool = False,
    as_of: str | None = None,
    event_after: str | None = None,
    event_before: str | None = None,
    ephemeral: bool | None = None,
) -> list[dict]:
    """Search memories using hybrid semantic search. YOUR PRIMARY KNOWLEDGE RETRIEVAL TOOL.

    TRIGGER — Use this when you encounter ANY of these patterns:
    - "how do we...", "where is...", "what's the command for..."
    - "did we...", "have we...", "was there...", "were there..."
    - "what port", "what host", "what path", "what URL"
    - "deploy", "configure", "set up", "install" (any infrastructure action)
    - "remind me", "what was", "tell me about", "show me"
    - "find", "look for", "search", "check", "review"
    - Any moment of uncertainty about facts, processes, or prior decisions

    CRITICAL: Search BEFORE guessing, before SSH-ing to figure it out, before
    asking the user. Memory search is faster and more reliable than exploration.
    This is not just for explicit "search" requests — use it whenever you need
    context you don't currently have.

    PATTERN: search (summaries) → recall (full content for specific IDs)

    Combines four signals via Reciprocal Rank Fusion (RRF):
    - Vector similarity (50%): finds conceptually similar content
    - Recency (20%): newer memories rank higher
    - Keyword matching (20%): catches exact terms
    - Tag matching (10%): categorical filtering

    Args:
        query: Natural language search query. Be specific — "deploy cairn production" not just "deploy".
        project: Filter to a specific project. Omit to search all (recommended for infrastructure/cross-cutting queries).
        memory_type: Filter by type (e.g., 'decision' for architecture choices, 'rule' for guardrails).
        search_mode: 'semantic' (hybrid RRF, default), 'keyword' (exact text), or 'vector' (embedding only).
        limit: Maximum results to return (default 10).
        include_full: Return full content (True) or summaries only (False, default).
        as_of: Bi-temporal filter: only return memories that existed at this point in time
            (transaction time — filters on created_at). ISO 8601 format.
        event_after: Bi-temporal filter: only return memories where the event occurred
            at or after this timestamp (valid time — filters on event_at). ISO 8601 format.
        event_before: Bi-temporal filter: only return memories where the event occurred
            at or before this timestamp (valid time — filters on event_at). ISO 8601 format.
        ephemeral: Lifecycle filter. True=only ephemeral (decaying salience),
            False=only crystallized (permanent), None=all memories (default).
    """
    try:
        validate_search(query, limit)
        if search_mode not in VALID_SEARCH_MODES:
            return [{"error": f"invalid search_mode: {search_mode}. Must be one of: {', '.join(VALID_SEARCH_MODES)}"}]

        def _do_search():
            results = search_engine.search(
                query=query,
                project=project,
                memory_type=memory_type,
                search_mode=search_mode,
                limit=limit,
                include_full=include_full,
                as_of=as_of,
                event_after=event_after,
                event_before=event_before,
                ephemeral=ephemeral,
            )

            # Apply budget cap
            budget = config.budget.search
            if budget > 0 and results:
                content_key = "content" if include_full else "summary"
                results_capped, meta = apply_list_budget(
                    results, budget, content_key,
                    per_item_max=BUDGET_SEARCH_PER_ITEM,
                    overflow_message=(
                        "...{omitted} more results omitted. "
                        "Use recall(ids=[...]) for full content, or narrow your query."
                    ),
                )
                if meta["omitted"] > 0:
                    results_capped.append({"_overflow": meta["overflow_message"]})
                results = results_capped

            # Publish search.executed event for access tracking
            if event_bus and results:
                try:
                    memory_ids = [r["id"] for r in results if isinstance(r, dict) and "id" in r]
                    event_bus.publish(
                        session_name="",
                        event_type="search.executed",
                        project=project,
                        payload={
                            "query": query[:200],
                            "result_count": len(memory_ids),
                            "memory_ids": memory_ids[:20],
                            "search_mode": search_mode,
                        },
                    )
                except Exception:
                    logger.debug("Failed to publish search.executed event", exc_info=True)

            # Confidence gating: wrap results with assessment when active
            confidence = search_engine.assess_confidence(query, results)
            if confidence is not None:
                return {"results": results, "confidence": confidence}
            return results

        return await _in_thread(_do_search)
    except ValidationError as e:
        return [{"error": str(e)}]
    except Exception as e:
        logger.exception("search failed")
        return [{"error": f"Internal error: {e}"}]


# ============================================================
# Tool 3: recall
# ============================================================

@mcp.tool()
async def recall(ids: list[int]) -> list[dict]:
    """Retrieve full content for specific memory IDs. Second step in progressive disclosure.

    WHEN TO USE: After search returns relevant summaries and you need the complete content.
    Search returns summaries to save context window; recall returns everything.

    PATTERN: Always follows search — don't guess IDs, search first to find them.

    TRIGGER: When a search result summary looks relevant but you need the full detail
    to answer the question or make a decision.

    Args:
        ids: List of memory IDs to retrieve (max 10 per call).
    """
    try:
        if not ids:
            return [{"error": "ids list is required and cannot be empty"}]
        if len(ids) > MAX_RECALL_IDS:
            return [{"error": f"Maximum {MAX_RECALL_IDS} IDs per recall. Batch into multiple calls."}]

        def _do_recall():
            results = memory_store.recall(ids)

            # Apply budget cap
            budget = config.budget.recall
            if budget > 0 and results:
                results_capped, meta = apply_list_budget(
                    results, budget, "content",
                    per_item_max=BUDGET_RECALL_PER_ITEM,
                    overflow_message=(
                        "...{omitted} memories truncated from response. "
                        "Recall fewer IDs per call for full content."
                    ),
                )
                if meta["omitted"] > 0:
                    results_capped.append({"_overflow": meta["overflow_message"]})
                results = results_capped
            # Publish memory.recalled event for access tracking
            if event_bus and results:
                try:
                    memory_ids = [r["id"] for r in results if isinstance(r, dict) and "id" in r]
                    event_bus.publish(
                        session_name="",
                        event_type="memory.recalled",
                        payload={
                            "memory_ids": memory_ids,
                            "count": len(memory_ids),
                        },
                    )
                except Exception:
                    logger.debug("Failed to publish memory.recalled event", exc_info=True)

            return results

        return await _in_thread(_do_recall)
    except Exception as e:
        logger.exception("recall failed")
        return [{"error": f"Internal error: {e}"}]


# ============================================================
# Tool 4: modify
# ============================================================

@mcp.tool()
async def modify(
    id: int,
    action: str,
    content: str | None = None,
    memory_type: str | None = None,
    importance: float | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
    project: str | None = None,
    author: str | None = None,
) -> dict:
    """Update, soft-delete, or reactivate a memory.

    WHEN TO USE:
    - Update outdated information (e.g., a deploy process changed)
    - Correct mistakes in stored memories
    - Inactivate obsolete content (soft-delete — recoverable)
    - Reactivate a previously inactivated memory

    PATTERN: search → recall → modify. Always find and verify the memory before modifying.

    TRIGGER: "update memory", "that's outdated", "fix that note", "remove that",
    "that's wrong", "archive that", "bring back"

    Actions:
    - 'update': Modify fields. Content changes trigger re-embedding.
    - 'inactivate': Soft-delete with a reason. Memory is hidden but recoverable.
    - 'reactivate': Restore an inactivated memory.

    Args:
        id: Memory ID to modify.
        action: One of 'update', 'inactivate', 'reactivate'.
        content: New content (update only). Triggers re-embedding.
        memory_type: New type classification (update only).
        importance: New importance score (update only).
        tags: New tags - replaces existing (update only).
        reason: Reason for inactivation (required for inactivate).
        project: Move memory to a different project (update only).
        author: Speaker attribution (update only). "user", "assistant", or a name.
    """
    try:
        if action not in MemoryAction.ALL:
            return {"error": f"invalid action: {action}. Must be one of: {', '.join(sorted(MemoryAction.ALL))}"}
        if content is not None and len(content) > MAX_CONTENT_SIZE:
            return {"error": f"content exceeds {MAX_CONTENT_SIZE} character limit"}
        if memory_type is not None and memory_type not in VALID_MEMORY_TYPES:
            return {"error": f"invalid memory_type: {memory_type}"}
        if importance is not None and not (0.0 <= importance <= 1.0):
            return {"error": "importance must be between 0.0 and 1.0"}

        def _do_modify():
            return memory_store.modify(
                memory_id=id,
                action=action,
                content=content,
                memory_type=memory_type,
                importance=importance,
                tags=tags,
                reason=reason,
                project=project,
                author=author,
            )

        return await _in_thread(_do_modify)
    except Exception as e:
        logger.exception("modify failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 5: rules
# ============================================================

@mcp.tool()
async def rules(project: str | None = None) -> list[dict]:
    """Get behavioral rules and guardrails.

    CRITICAL: Call this at session start. Rules define how you should behave —
    deployment patterns, communication style, project conventions, safety guardrails.

    WHEN TO USE:
    - Session startup (ALWAYS — this is step 1 of the boot sequence)
    - Switching to a new project mid-session
    - Before taking an action you're unsure about (rules may have guidance)

    Returns rule-type memories from __global__ (universal guardrails) and
    the specified project. Rules guide agent behavior and are loaded at
    session start.

    Args:
        project: Project name to get rules for. Omit for global rules only.
    """
    try:
        def _do_rules():
            result = memory_store.get_rules(project)
            items = result["items"]
            budget = config.budget.rules
            if budget > 0 and items:
                items, meta = apply_list_budget(
                    items, budget, "content",
                    per_item_max=BUDGET_RULES_PER_ITEM,
                    overflow_message=(
                        "...{omitted} more rules omitted. "
                        "Use search(query='topic', memory_type='rule') for targeted retrieval."
                    ),
                )
                if meta["omitted"] > 0:
                    items.append({"_overflow": meta["overflow_message"]})
            return items

        return await _in_thread(_do_rules)
    except Exception as e:
        logger.exception("rules failed")
        return [{"error": f"Internal error: {e}"}]


# ============================================================
# Tool 6: insights
# ============================================================

@mcp.tool()
async def insights(
    project: str | None = None,
    topic: str | None = None,
    min_confidence: float = 0.5,
    limit: int = 10,
) -> dict:
    """Discover patterns across stored memories using semantic clustering.

    TRIGGER: When the user wants meta-analysis or pattern discovery:
    - "what patterns", "what trends", "what's recurring", "common themes"
    - "best practices", "what can we learn from", "how has X evolved"
    - "analyze across", "cross-project", "what do these have in common"

    WHEN TO USE: For big-picture analysis, not simple lookups (use search for those).
    Proactively use during complex discussions to surface patterns the user hasn't noticed.

    Uses HDBSCAN to group semantically similar memories into clusters, then
    generates labels and summaries for each cluster. Clustering runs lazily:
    only when stale (>24h, >20% growth, or first run).

    Args:
        project: Filter to a specific project. Omit for cross-project analysis.
        topic: Optional topic to filter clusters by semantic similarity.
        min_confidence: Minimum cluster confidence score (0.0-1.0, default 0.5).
        limit: Maximum clusters to return (default 10).
    """
    try:
        def _do_insights():
            # Check staleness and recluster if needed
            reclustered = False
            labeling_error = None
            if cluster_engine.is_stale(project):
                cluster_result = cluster_engine.run_clustering(project)
                reclustered = True
                labeling_error = cluster_result.get("labeling_error")

            # Fetch clusters
            clusters = cluster_engine.get_clusters(
                project=project,
                topic=topic,
                min_confidence=min_confidence,
                limit=limit,
            )

            last_run = cluster_engine.get_last_run(project)

            # Apply budget cap to cluster summaries
            budget = config.budget.insights
            overflow_msg = ""
            if budget > 0 and clusters:
                clusters, meta = apply_list_budget(
                    clusters, budget, "summary",
                    per_item_max=BUDGET_INSIGHTS_PER_ITEM,
                    overflow_message=(
                        "...{omitted} clusters omitted. "
                        "Use a topic filter or increase limit for targeted results."
                    ),
                )
                if meta["omitted"] > 0:
                    overflow_msg = meta["overflow_message"]

            result = {
                "status": "reclustered" if reclustered else "cached",
                "cluster_count": len(clusters),
                "clusters": clusters,
                "last_clustered_at": last_run["created_at"] if last_run else None,
            }
            if labeling_error:
                result["labeling_warning"] = labeling_error
            if overflow_msg:
                result["_overflow"] = overflow_msg
            return result

        return await _in_thread(_do_insights)
    except Exception as e:
        logger.exception("insights failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 7: projects
# ============================================================

@mcp.tool()
async def projects(
    action: str,
    project: str | None = None,
    doc_type: str | None = None,
    content: str | None = None,
    doc_id: int | None = None,
    title: str | None = None,
    target: str | None = None,
    link_type: str = "related",
    file_path: str | None = None,
) -> dict | list[dict]:
    """Manage project documents and relationships. For formal project docs, NOT working notes.

    WHEN TO USE:
    - Creating or updating project briefs, PRDs, plans, primers, writeups, guides
    - Linking related projects together
    - Listing all projects for orientation
    - User asks "what projects do we have", "show me the brief for X"

    DON'T USE FOR: Working notes, progress updates, decisions, learnings — use store() for those.

    Actions:
    - 'list': List all projects with memory counts.
    - 'create_doc': Create a project document (brief, PRD, plan, primer, writeup, or guide).
    - 'get_docs': Get documents for a project, optionally filtered by type.
    - 'update_doc': Update an existing document's content.
    - 'link': Link two projects together.
    - 'get_links': Get all links for a project.

    Args:
        action: One of 'list', 'create_doc', 'get_docs', 'update_doc', 'link', 'get_links'.
        project: Project name (required for all actions except 'list').
        doc_type: Document type: 'brief', 'prd', 'plan', 'primer', 'writeup', or 'guide' (for create_doc, optional for get_docs).
        content: Document content (required for create_doc, update_doc). Can be omitted if file_path is provided.
        doc_id: Document ID (required for update_doc).
        title: Optional document title (for create_doc, update_doc).
        target: Target project name (required for link).
        link_type: Relationship type for link (default 'related').
        file_path: Path to a local file in the server's ingest staging directory.
            Use instead of content to ingest from a staging directory (avoids inline transfer).
    """
    try:
        if not project and action != "list":
            return {"error": "project is required for this action"}

        def _do_projects():
            nonlocal content, title

            # Resolve file_path for create_doc/update_doc
            if file_path and not content and action in ("create_doc", "update_doc"):
                file_content, inferred_title = ingest_pipeline.read_local_file(file_path)
                content = file_content
                if not title:
                    title = inferred_title

            if action == "list":
                return project_manager.list_all()["items"]

            if action == "create_doc":
                if not doc_type or not content:
                    return {"error": "doc_type and content are required for create_doc"}
                return project_manager.create_doc(project, doc_type, content, title=title)

            if action == "get_docs":
                return project_manager.get_docs(project, doc_type=doc_type)

            if action == "update_doc":
                if not doc_id or not content:
                    return {"error": "doc_id and content are required for update_doc"}
                return project_manager.update_doc(doc_id, content, title=title)

            if action == "link":
                if not target:
                    return {"error": "target project is required for link"}
                return project_manager.link(project, target, link_type)

            if action == "get_links":
                return project_manager.get_links(project)

            return {"error": f"Unknown action: {action}"}

        return await _in_thread(_do_projects)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("projects failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 8: tasks
# ============================================================

@mcp.tool()
async def tasks(
    action: str,
    project: str,
    description: str | None = None,
    task_id: int | None = None,
    memory_ids: list[int] | None = None,
    include_completed: bool = False,
) -> dict | list[dict]:
    """DEPRECATED: Use working_memory() for loose thoughts or work_items() for structured work.

    Personal reminders and TODO items — human-only quick capture.
    This tool is deprecated as of v0.67.0. Use working_memory(action="capture")
    for hypotheses, questions, and loose threads. Use work_items(action="create")
    for structured, trackable work.

    Existing tasks continue to work. No data is deleted.

    Actions:
    - 'create': Create a new personal reminder/task.
    - 'complete': Mark a task as done.
    - 'list': List tasks for a project.
    - 'link_memories': Associate memories with a task.
    - 'promote': Promote a task to a work item. Creates a work item with the
      task description, marks the task completed, transfers linked memories,
      and logs a "promoted" activity on the new work item.

    Args:
        action: One of 'create', 'complete', 'list', 'link_memories', 'promote'.
        project: Project name.
        description: Task description (required for create).
        task_id: Task ID (required for complete, link_memories, promote).
        memory_ids: Memory IDs to link (required for link_memories).
        include_completed: Include completed tasks in list (default false).
    """
    try:
        def _do_tasks():
            if action == "create":
                if not description:
                    return {"error": "description is required for create"}
                return task_manager.create(project, description)

            if action == "complete":
                if not task_id:
                    return {"error": "task_id is required for complete"}
                return task_manager.complete(task_id)

            if action == "list":
                return task_manager.list_tasks(project, include_completed=include_completed)["items"]

            if action == "link_memories":
                if not task_id or not memory_ids:
                    return {"error": "task_id and memory_ids are required for link_memories"}
                return task_manager.link_memories(task_id, memory_ids)

            if action == "promote":
                if not task_id:
                    return {"error": "task_id is required for promote"}

                # 1. Fetch and validate task
                task_row = db.execute_one(
                    """SELECT t.id, t.description, t.status, p.name AS project
                       FROM tasks t
                       LEFT JOIN projects p ON t.project_id = p.id
                       WHERE t.id = %s""",
                    (task_id,),
                )
                if not task_row:
                    return {"error": f"Task {task_id} not found"}
                if task_row["status"] != "pending":
                    return {"error": f"Task {task_id} is already {task_row['status']}"}

                task_project = task_row["project"] or project

                # 2. Create work item from task description
                wi = work_item_manager.create(
                    project=task_project,
                    title=task_row["description"],
                    item_type="task",
                )

                # 3. Mark task completed
                task_manager.complete(task_id)

                # 4. Transfer linked memories
                linked = db.execute(
                    "SELECT memory_id FROM task_memory_links WHERE task_id = %s",
                    (task_id,),
                )
                linked_ids = [r["memory_id"] for r in linked]
                if linked_ids:
                    work_item_manager.link_memories(wi["id"], linked_ids)

                # 5. Log promoted activity
                work_item_manager._log_activity(
                    wi["id"],
                    actor="system",
                    activity_type=ActivityType.PROMOTED,
                    content=f"Promoted from task #{task_id}",
                    metadata={"source_task_id": task_id},
                )

                return {"action": "promoted", "task_id": task_id, "work_item": wi}

            return {"error": f"Unknown action: {action}"}

        return await _in_thread(_do_tasks)
    except Exception as e:
        logger.exception("tasks failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 17: work_items
# ============================================================

@mcp.tool()
async def work_items(
    action: str,
    project: str | None = None,
    title: str | None = None,
    description: str | None = None,
    item_type: str | None = None,
    priority: int | None = None,
    parent_id: int | None = None,
    work_item_id: int | str | None = None,
    blocker_id: int | str | None = None,
    blocked_id: int | str | None = None,
    assignee: str | None = None,
    status: str | None = None,
    session_name: str | None = None,
    metadata: dict | None = None,
    acceptance_criteria: str | None = None,
    memory_ids: list[int] | None = None,
    include_children: bool = False,
    limit: int = 20,
    offset: int = 0,
    gate_type: str | None = None,
    gate_data: dict | None = None,
    gate_response: dict | None = None,
    risk_tier: int | None = None,
    constraints: dict | None = None,
    actor: str | None = None,
    note: str | None = None,
) -> dict | list[dict]:
    """Work tracking with hierarchy, dependencies, and agent dispatch.

    Actions (required params in parens):
    - 'create': New item (project, title). Optional: description, item_type, priority, risk_tier, constraints.
    - 'update': Modify fields (work_item_id). Any field can be updated.
    - 'list': Filtered list. Optional: project, status, item_type, assignee, limit, offset.
    - 'get': Full detail (work_item_id).
    - 'complete': Mark done + auto-unblock dependents (work_item_id).
    - 'claim': Assign to agent/person (work_item_id, assignee).
    - 'add_child': Add subtask (work_item_id as parent, title).
    - 'block'/'unblock': Manage dependencies (blocker_id, blocked_id).
    - 'ready': Dispatch queue — unblocked, unassigned items (project).
    - 'link_memories': Attach context (work_item_id, memory_ids).
    - 'set_gate': Block on human input (work_item_id, gate_type). Optional: gate_data, actor.
    - 'resolve_gate': Unblock (work_item_id). Optional: gate_response, actor.
    - 'heartbeat': Agent progress (work_item_id, assignee). Optional: state, note.
    - 'activity': History log (work_item_id).
    - 'briefing': Agent dispatch context (work_item_id).
    - 'decompose': Epic decomposition context — briefing + existing children (work_item_id).
    - 'progress': Subtask progress summary — status counts, stale agents, blocked items (work_item_id).
    - 'analyze': Anti-pattern detection on epic children — Split Keel, Drifting Anchorage, Skeleton Crew (work_item_id).
    - 'gated': Items awaiting gates. Optional: project, gate_type.
    - 'deliverable': Get deliverable for a work item (work_item_id).
    - 'create_deliverable': Create a deliverable (work_item_id, description as summary). Optional: metadata for changes/decisions/open_items.
    - 'review_deliverable': Approve/revise/reject (work_item_id, gate_type as action: approve/revise/reject). Optional: note, actor.
    - 'submit_deliverable': Submit draft for review (work_item_id).
    - 'pending_deliverables': List deliverables needing review. Optional: project, limit, offset.
    - 'synthesize': Create epic deliverable from child deliverables (work_item_id). Optional: description as summary override.
    - 'child_deliverables': Collect latest deliverables from all children (work_item_id).
    - 'lock': Acquire file locks (project, work_item_id, assignee). metadata.paths = list of file paths.
    - 'unlock': Release file locks. Provide work_item_id or assignee or metadata.paths.
    - 'check_locks': Check for conflicts (project). metadata.paths = list of paths. Optional: assignee.
    - 'list_locks': List active locks (project). Optional: assignee, work_item_id.
    - 'suggest_agent': Affinity-based agent suggestion for a work item (work_item_id or project+title+description).
    """
    try:
        def _do_work_items():
            if action == "create":
                if not project or not title:
                    return {"error": "project and title are required for create"}
                return work_item_manager.create(
                    project=project, title=title, description=description,
                    item_type=item_type or "task", priority=priority or 0,
                    parent_id=parent_id, session_name=session_name,
                    metadata=metadata, acceptance_criteria=acceptance_criteria,
                    constraints=constraints, risk_tier=risk_tier,
                )

            if action == "update":
                if not work_item_id:
                    return {"error": "work_item_id is required for update"}
                fields = {}
                if session_name is not None:
                    fields["_calling_session"] = session_name
                if title is not None:
                    fields["title"] = title
                if description is not None:
                    fields["description"] = description
                if status is not None:
                    fields["status"] = status
                if priority is not None:
                    fields["priority"] = priority
                if assignee is not None:
                    fields["assignee"] = assignee
                if acceptance_criteria is not None:
                    fields["acceptance_criteria"] = acceptance_criteria
                if item_type is not None:
                    fields["item_type"] = item_type
                if session_name is not None:
                    fields["session_name"] = session_name
                if metadata is not None:
                    fields["metadata"] = metadata
                if risk_tier is not None:
                    fields["risk_tier"] = risk_tier
                if constraints is not None:
                    fields["constraints"] = constraints
                if parent_id is not None:
                    fields["parent_id"] = parent_id
                return work_item_manager.update(work_item_id, **fields)

            if action == "claim":
                if not work_item_id or not assignee:
                    return {"error": "work_item_id and assignee are required for claim"}
                return work_item_manager.claim(work_item_id, assignee, session_name=session_name)

            if action == "complete":
                if not work_item_id:
                    return {"error": "work_item_id is required for complete"}
                result = work_item_manager.complete(work_item_id, session_name=session_name)
                # Auto-release locks held by this work item (ca-156)
                if project:
                    released = _lock_manager.release(
                        project, work_item_id=str(work_item_id),
                    )
                    if released:
                        result["locks_released"] = released
                return result

            if action == "add_child":
                if not work_item_id or not title:
                    return {"error": "work_item_id (parent) and title are required for add_child"}
                return work_item_manager.add_child(
                    parent_id=work_item_id, title=title, description=description,
                    priority=priority or 0, session_name=session_name,
                    metadata=metadata, acceptance_criteria=acceptance_criteria,
                    constraints=constraints, risk_tier=risk_tier,
                )

            if action == "block":
                if not blocker_id or not blocked_id:
                    return {"error": "blocker_id and blocked_id are required for block"}
                return work_item_manager.block(blocker_id, blocked_id)

            if action == "unblock":
                if not blocker_id or not blocked_id:
                    return {"error": "blocker_id and blocked_id are required for unblock"}
                return work_item_manager.unblock(blocker_id, blocked_id)

            if action == "list":
                return work_item_manager.list_items(
                    project=project, status=status, item_type=item_type,
                    assignee=assignee, parent_id=parent_id,
                    include_children=include_children,
                    limit=min(limit, MAX_LIMIT), offset=offset,
                )

            if action == "ready":
                if not project:
                    return {"error": "project is required for ready"}
                return work_item_manager.ready_queue(project, limit=min(limit, MAX_LIMIT))

            if action == "get":
                if not work_item_id:
                    return {"error": "work_item_id is required for get"}
                return work_item_manager.get(work_item_id)

            if action == "link_memories":
                if not work_item_id or not memory_ids:
                    return {"error": "work_item_id and memory_ids are required for link_memories"}
                return work_item_manager.link_memories(work_item_id, memory_ids)

            if action == "set_gate":
                if not work_item_id or not gate_type:
                    return {"error": "work_item_id and gate_type are required for set_gate"}
                return work_item_manager.set_gate(
                    work_item_id, gate_type, gate_data=gate_data, actor=actor,
                )

            if action == "resolve_gate":
                if not work_item_id:
                    return {"error": "work_item_id is required for resolve_gate"}
                return work_item_manager.resolve_gate(
                    work_item_id, response=gate_response, actor=actor,
                )

            if action == "heartbeat":
                if not work_item_id or not assignee:
                    return {"error": "work_item_id and assignee are required for heartbeat"}
                return work_item_manager.heartbeat(
                    work_item_id, assignee, state=status or "working", note=note,
                    session_name=session_name,
                )

            if action == "activity":
                if not work_item_id:
                    return {"error": "work_item_id is required for activity"}
                return work_item_manager.get_activity(
                    work_item_id, limit=min(limit, MAX_LIMIT), offset=offset,
                )

            if action == "briefing":
                if not work_item_id:
                    return {"error": "work_item_id is required for briefing"}
                return work_item_manager.generate_briefing(work_item_id)

            if action == "decompose":
                if not work_item_id:
                    return {"error": "work_item_id is required for decompose"}
                return work_item_manager.decomposition_context(work_item_id)

            if action == "progress":
                if not work_item_id:
                    return {"error": "work_item_id is required for progress"}
                return work_item_manager.progress_summary(work_item_id)

            if action == "analyze":
                if not work_item_id:
                    return {"error": "work_item_id (parent) is required for analyze"}
                from cairn.core.antipatterns import analyze_epic
                decomp = work_item_manager.decomposition_context(work_item_id)
                return analyze_epic(
                    decomp.get("existing_children", []),
                    original_count=metadata.get("original_count") if metadata else None,
                )

            if action == "gated":
                return work_item_manager.gated_items(
                    project=project, gate_type=gate_type, limit=min(limit, MAX_LIMIT),
                )

            # Deliverable actions
            if action == "deliverable":
                if not work_item_id:
                    return {"error": "work_item_id is required for deliverable"}
                result = deliverable_manager.get(int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id)
                return result or {"error": f"No deliverable found for work item {work_item_id}"}

            if action == "create_deliverable":
                if not work_item_id:
                    return {"error": "work_item_id is required for create_deliverable"}
                wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                return deliverable_manager.create(
                    work_item_id=wi_id,
                    summary=description or "",
                    changes=metadata.get("changes") if metadata else None,
                    decisions=metadata.get("decisions") if metadata else None,
                    open_items=metadata.get("open_items") if metadata else None,
                    metrics=metadata.get("metrics") if metadata else None,
                    status=status or "draft",
                )

            if action == "review_deliverable":
                if not work_item_id:
                    return {"error": "work_item_id is required for review_deliverable"}
                review_action = gate_type  # reuse gate_type param for review action
                if review_action not in ("approve", "revise", "reject"):
                    return {"error": "gate_type must be 'approve', 'revise', or 'reject' for review_deliverable"}
                wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                return deliverable_manager.review(
                    work_item_id=wi_id,
                    action=review_action,
                    reviewer=actor,
                    notes=note,
                )

            if action == "submit_deliverable":
                if not work_item_id:
                    return {"error": "work_item_id is required for submit_deliverable"}
                wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                return deliverable_manager.submit_for_review(wi_id)

            if action == "pending_deliverables":
                return deliverable_manager.list_pending(
                    project=project, limit=min(limit, MAX_LIMIT), offset=offset,
                )

            if action == "synthesize":
                if not work_item_id:
                    return {"error": "work_item_id (parent epic) is required for synthesize"}
                wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                return deliverable_manager.synthesize_epic(
                    wi_id, summary_override=description,
                )

            if action == "child_deliverables":
                if not work_item_id:
                    return {"error": "work_item_id (parent) is required for child_deliverables"}
                wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                return {"items": deliverable_manager.collect_child_deliverables(wi_id)}

            # --- Resource locking (ca-156) ---

            if action == "lock":
                if not project:
                    return {"error": "project is required for lock"}
                paths = (metadata or {}).get("paths")
                if not paths or not isinstance(paths, list):
                    return {"error": "metadata.paths (list of file paths) is required for lock"}
                owner = assignee or "unknown"
                wi_display = str(work_item_id) if work_item_id else "untracked"
                conflicts = _lock_manager.acquire(project, paths, owner, wi_display)
                if conflicts:
                    return {
                        "acquired": False,
                        "conflicts": [c.to_dict() for c in conflicts],
                    }
                return {"acquired": True, "paths": paths, "owner": owner}

            if action == "unlock":
                if not project:
                    return {"error": "project is required for unlock"}
                paths = (metadata or {}).get("paths")
                wi_display = str(work_item_id) if work_item_id else None
                released = _lock_manager.release(
                    project,
                    paths=paths if isinstance(paths, list) else None,
                    work_item_id=wi_display,
                    owner=assignee,
                )
                return {"released": released}

            if action == "check_locks":
                if not project:
                    return {"error": "project is required for check_locks"}
                paths = (metadata or {}).get("paths")
                if not paths or not isinstance(paths, list):
                    return {"error": "metadata.paths (list of file paths) is required for check_locks"}
                conflicts = _lock_manager.check(project, paths, owner=assignee)
                return {
                    "clear": len(conflicts) == 0,
                    "conflicts": [c.to_dict() for c in conflicts],
                }

            if action == "list_locks":
                if not project:
                    return {"error": "project is required for list_locks"}
                locks = _lock_manager.list_locks(
                    project,
                    owner=assignee,
                    work_item_id=str(work_item_id) if work_item_id else None,
                )
                return {"locks": [l.to_dict() for l in locks]}

            if action == "suggest_agent":
                from cairn.core.affinity import rank_agents
                from cairn.core.agents import AgentRegistry
                registry = AgentRegistry()
                # Build work item dict from available params
                wi_dict = {}
                if work_item_id:
                    wi_dict = work_item_manager.get(work_item_id)
                else:
                    wi_dict = {
                        "project": project, "title": title,
                        "description": description,
                        "item_type": item_type or "task",
                        "risk_tier": risk_tier,
                    }
                ranked = rank_agents(registry, wi_dict)
                return {
                    "suggestions": [s.to_dict() for s in ranked if not s.disqualified],
                    "disqualified": [s.to_dict() for s in ranked if s.disqualified],
                }

            return {"error": f"Unknown action: {action}"}

        return await _in_thread(_do_work_items)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("work_items failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 9: dispatch
# ============================================================

@mcp.tool()
async def dispatch(
    work_item_id: int | str | None = None,
    project: str | None = None,
    title: str | None = None,
    description: str | None = None,
    backend: str | None = None,
    risk_tier: int | None = None,
    model: str | None = None,
    agent: str | None = None,
    assignee: str | None = None,
) -> dict:
    """Dispatch work to a background agent — tracked, briefed, heartbeating.

    USE THIS instead of native subagents (Task tool) when:
    - The work will take more than a few minutes
    - You want the job tracked (visible in cairn-ui, queryable, resumable)
    - You want to continue working on other things in parallel
    - The task involves a different codebase or working directory
    - You want heartbeat monitoring and gate support

    DO NOT USE when:
    - The task is quick (< 2 minutes) and you need the result immediately
    - You're doing a simple lookup or computation

    Two modes:
    - Dispatch an existing work item: pass work_item_id
    - Create + dispatch in one shot: pass project + title (+ optional description)

    Internally: creates/resolves work item → claims it → generates briefing →
    creates workspace session → sends briefing to agent. One call does it all.

    The dispatched agent gets Cairn MCP access and will heartbeat progress
    back. Check status via work_items(action='get', work_item_id=...).

    Args:
        work_item_id: Existing work item to dispatch (display_id like 'ca-42' or numeric ID).
        project: Project name (required if creating a new work item).
        title: Work item title (required if creating a new work item).
        description: Detailed description of the work to be done.
        backend: Agent backend: 'claude_code' or 'opencode'. Auto-selects if omitted.
        risk_tier: Permission level (0=full autonomy, 1=broad, 2=read-heavy, 3=research-only).
        model: Model override for Claude Code (e.g. 'claude-sonnet-4-6').
        agent: Agent definition to use (defaults to workspace config).
        assignee: Name for the agent claim (auto-generated if omitted).
    """
    try:
        if workspace_manager is None:
            return {"error": "workspace manager not available"}
        return await _in_thread(
            workspace_manager.dispatch,
            work_item_id=work_item_id,
            project=project,
            title=title,
            description=description,
            backend=backend,
            risk_tier=risk_tier,
            model=model,
            agent=agent,
            assignee=assignee,
        )
    except Exception as e:
        logger.exception("dispatch failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 10: think
# ============================================================

@mcp.tool()
async def think(
    action: str,
    project: str,
    goal: str | None = None,
    sequence_id: int | None = None,
    thought: str | None = None,
    thought_type: str = "general",
    branch_name: str | None = None,
    author: str | None = None,
) -> dict | list[dict]:
    """Structured thinking sequences for collaborative reasoning.

    TRIGGER: When a problem has multiple valid approaches or needs step-by-step analysis:
    - "think through", "analyze", "reason about", "let's consider"
    - Architecture decisions with trade-offs
    - Debugging complex issues (hypothesis → test → observe → conclude)
    - Planning multi-step implementations
    - Any problem where the user wants to participate in the reasoning

    This is a COLLABORATIVE tool — both humans and agents contribute thoughts.
    Use author to attribute who contributed each thought. The exploration
    itself becomes searchable knowledge.

    PATTERN: start (with goal) → add thoughts (observations, hypotheses, analysis) → conclude
    Use 'alternative' or 'branch' thought_type to explore divergent paths.
    Use 'reopen' to resume a completed sequence across sessions.

    WHEN NOT TO USE: Simple questions (use search), straightforward tasks, quick lookups.

    Actions:
    - 'start': Begin a new thinking sequence with a goal.
    - 'add': Add a thought to an active sequence.
    - 'conclude': Finalize a sequence with a conclusion.
    - 'reopen': Reopen a completed sequence for continued thinking.
    - 'get': Retrieve a full sequence with all thoughts.
    - 'list': List thinking sequences for a project.
    - 'summarize': Structured deliberation summary — decisions, tradeoffs, risks, dependencies (sequence_id).

    Args:
        action: One of 'start', 'add', 'conclude', 'reopen', 'get', 'list'.
        project: Project name.
        goal: The problem or goal (required for start).
        sequence_id: Sequence ID (required for add, conclude, reopen, get).
        thought: The thought content (required for add, conclude).
        thought_type: Type: observation, hypothesis, question, reasoning, conclusion,
                      assumption, analysis, general, alternative, branch,
                      insight, realization, pattern, challenge, response.
        branch_name: Name for a branch when thought_type is alternative/branch.
        author: Who contributed this thought (e.g., "human", "assistant", a name).
    """
    try:
        def _do_think():
            if action == "start":
                if not goal:
                    return {"error": "goal is required for start"}
                return thinking_engine.start(project, goal)

            if action == "add":
                if not sequence_id or not thought:
                    return {"error": "sequence_id and thought are required for add"}
                return thinking_engine.add_thought(sequence_id, thought, thought_type, branch_name, author)

            if action == "conclude":
                if not sequence_id or not thought:
                    return {"error": "sequence_id and thought (conclusion) are required for conclude"}
                return thinking_engine.conclude(sequence_id, thought, author)

            if action == "reopen":
                if not sequence_id:
                    return {"error": "sequence_id is required for reopen"}
                return thinking_engine.reopen(sequence_id)

            if action == "get":
                if not sequence_id:
                    return {"error": "sequence_id is required for get"}
                return thinking_engine.get_sequence(sequence_id)

            if action == "list":
                return thinking_engine.list_sequences(project)["items"]

            if action == "summarize":
                if not sequence_id:
                    return {"error": "sequence_id is required for summarize"}
                return thinking_engine.summarize_deliberation(sequence_id)

            return {"error": f"Unknown action: {action}"}

        return await _in_thread(_do_think)
    except Exception as e:
        logger.exception("think failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 10: status
# ============================================================

@mcp.tool()
async def status() -> dict:
    """System health and statistics.

    WHEN TO USE: Health checks, system overview, "how many memories", "is cairn working",
    verifying deployment status. Quick diagnostic tool — no parameters required.
    """
    try:
        return await _in_thread(get_status, db, config)
    except Exception as e:
        logger.exception("status failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool: consolidate
# ============================================================

@mcp.tool()
async def consolidate(
    project: str,
    dry_run: bool = True,
    mode: str = "dedup",
) -> dict:
    """Review project memories for duplicates and recommend consolidation actions.

    WHEN TO USE: Memory maintenance — cleaning up duplicate or overlapping memories.
    - "clean up memories", "find duplicates", "consolidate", "too many similar notes"
    - Periodic housekeeping after intensive work sessions

    Finds semantically similar memory pairs (>0.85 cosine similarity), then asks LLM
    to recommend merges, promotions to rules, or inactivations. Dry run by default —
    always preview before applying.

    Args:
        project: Project name to consolidate.
        dry_run: If True (default), only recommend. If False, apply changes.
        mode: 'dedup' (find and merge duplicates) or 'synthesize' (cluster related
            memories and create higher-order insights). Default: dedup.
    """
    try:
        if not project or not project.strip():
            return {"error": "project is required"}
        if consolidation_engine is None:
            return {"error": "consolidation engine not available"}
        if mode == "synthesize":
            return await _in_thread(
                consolidation_engine.synthesize, project, dry_run=dry_run,
                cluster_engine=cluster_engine,
                memory_store=memory_store,
                event_bus=event_bus,
                config=config.consolidation_worker,
            )
        return await _in_thread(
            consolidation_engine.consolidate, project, dry_run=dry_run,
        )
    except Exception as e:
        logger.exception("consolidate failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool: decay_scan
# ============================================================

@mcp.tool()
async def decay_scan(
    project: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Scan for memories at risk of being forgotten by the decay system.

    WHEN TO USE: Understanding what the decay system would forget.
    - "what memories are decaying", "show me at-risk memories"
    - Verifying decay thresholds before enabling live mode

    Returns candidates with decay scores and protected status.
    Always dry-run by default — never forgets on its own.

    Args:
        project: Optional project filter.
        dry_run: Always True for this tool (inspection only).
    """
    try:
        if not _svc or not _svc.decay_worker:
            return {"error": "DecayWorker is not enabled"}
        return await _in_thread(_svc.decay_worker.scan)
    except Exception as e:
        logger.exception("decay_scan failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool: beliefs
# ============================================================

@mcp.tool()
async def beliefs(
    action: str,
    project: str,
    content: str | None = None,
    domain: str | None = None,
    confidence: float = 0.7,
    evidence_ids: list[int] | None = None,
    agent_name: str | None = None,
    belief_id: int | None = None,
    reason: str | None = None,
    confidence_delta: float = -0.1,
) -> dict:
    """Manage durable beliefs — post-decisional knowledge with confidence tracking.

    Beliefs are things an agent or the organization holds as true through experience.
    They have confidence scores, domain tags, evidence linking, and can be challenged
    or retracted. Beliefs are the downstream of working memory — hypotheses that
    crystallized, tensions that resolved, observations that solidified.

    Actions:
    - 'crystallize': Create a new belief (project, content). Optional: domain, confidence,
      evidence_ids, agent_name.
    - 'list': List beliefs (project). Optional: agent_name, domain, status.
    - 'get': Get full detail (belief_id).
    - 'challenge': Lower confidence on a belief (belief_id). Optional: evidence_id,
      reason, confidence_delta.
    - 'retract': Mark a belief as wrong (belief_id). Optional: reason.

    Args:
        action: One of 'crystallize', 'list', 'get', 'challenge', 'retract'.
        project: Project name.
        content: Belief content (required for crystallize).
        domain: Area of expertise (deployment, architecture, etc.).
        confidence: Initial confidence 0.0-1.0 (crystallize only).
        evidence_ids: Memory IDs supporting or challenging the belief.
        agent_name: Who holds this belief (None = organizational).
        belief_id: Belief ID (required for get, challenge, retract).
        reason: Explanation for challenge or retraction.
        confidence_delta: How much to adjust confidence on challenge (default -0.1).
    """
    try:
        if not belief_store:
            return {"error": "BeliefStore not initialized"}

        if action == "crystallize":
            if not content:
                return {"error": "content is required for crystallize"}
            return await _in_thread(
                belief_store.crystallize, project, content,
                domain=domain, confidence=confidence,
                evidence_ids=evidence_ids, agent_name=agent_name,
            )
        elif action == "list":
            return await _in_thread(
                belief_store.list_beliefs, project,
                agent_name=agent_name, domain=domain,
            )
        elif action == "get":
            if belief_id is None:
                return {"error": "belief_id is required for get"}
            result = await _in_thread(belief_store.get, belief_id)
            return result or {"error": f"Belief {belief_id} not found"}
        elif action == "challenge":
            if belief_id is None:
                return {"error": "belief_id is required for challenge"}
            return await _in_thread(
                belief_store.challenge, belief_id,
                evidence_id=evidence_ids[0] if evidence_ids else None,
                reason=reason, confidence_delta=confidence_delta,
            )
        elif action == "retract":
            if belief_id is None:
                return {"error": "belief_id is required for retract"}
            return await _in_thread(
                belief_store.retract, belief_id, reason=reason,
            )
        else:
            return {"error": f"Unknown action '{action}'. Use: crystallize, list, get, challenge, retract"}
    except Exception as e:
        logger.exception("beliefs failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Trail helper — delegates to shared orient module
# ============================================================

def _fetch_trail_data(
    project: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> dict:
    """Fetch recent activity trail data. Used by trail() tool."""
    from cairn.core.orient import fetch_trail_data
    return fetch_trail_data(
        db=db, graph_provider=graph_provider,
        project=project, since=since, limit=limit,
    )


# ============================================================
# Tool: orient
# ============================================================

@mcp.tool()
async def orient(project: str | None = None) -> dict:
    """Single-pass session boot. Returns rules, trail, learnings, and work items.

    Replaces calling rules() + search() + work_items() individually with one call.
    Each section gets a token budget allocation with surplus flowing to the next.

    Use this at session start. Individual tools remain available for granular
    use mid-session.

    Args:
        project: Project name for scoped rules and work items. Omit for global-only boot.
    """
    from cairn.core.orient import run_orient

    try:
        def _do_orient():
            return run_orient(
                project=project,
                config=config,
                db=db,
                memory_store=memory_store,
                search_engine=search_engine,
                work_item_manager=work_item_manager,
                task_manager=task_manager,
                graph_provider=graph_provider,
                belief_store=belief_store,
            )

        return await _in_thread(_do_orient)
    except Exception as e:
        logger.exception("orient failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 15: working_memory
# ============================================================

@mcp.tool()
async def working_memory(
    action: str,
    project: str | None = None,
    content: str | None = None,
    item_type: str | None = None,
    salience: float | None = None,
    author: str | None = None,
    session_name: str | None = None,
    item_id: int | None = None,
    resolved_into: str | None = None,
    resolution_id: str | None = None,
    resolution_note: str | None = None,
    min_salience: float = 0.0,
    limit: int = 20,
    offset: int = 0,
) -> dict | list[dict]:
    """Persistent working memory — active cognitive workspace that persists across sessions.

    Stores pre-crystallized cognitive items: hypotheses, questions, tensions,
    connections, threads, intuitions. These are NOT tasks, NOT memories, NOT beliefs.
    They're the half-formed thoughts and active cognitive threads that represent
    what you're currently thinking about.

    TRIGGER: When you notice something interesting but aren't ready to act:
    - "I think X might be causing Y" -> capture as hypothesis
    - "Why does this happen?" -> capture as question
    - "Something feels wrong about this" -> capture as tension or intuition
    - "This reminds me of..." -> capture as connection
    - "I was in the middle of..." -> capture as thread

    Shared space: both agent and human items live in the same pool per project.

    Actions:
    - 'capture': Store a new cognitive item (project, content). Optional: item_type, salience, author, session_name.
    - 'list': List active items (project). Optional: author, item_type, min_salience, limit, offset.
    - 'get': Full detail for an item (item_id).
    - 'resolve': Mark resolved into concrete entity (item_id, resolved_into). Optional: resolution_id, resolution_note.
    - 'pin': Prevent salience decay (item_id).
    - 'unpin': Resume salience decay (item_id).
    - 'boost': Engaged with item — boost salience (item_id).
    - 'archive': Manually archive (item_id).

    Args:
        action: One of 'capture', 'list', 'get', 'resolve', 'pin', 'unpin', 'boost', 'archive'.
        project: Project name (required for capture, list).
        content: The cognitive item content (required for capture).
        item_type: hypothesis, question, tension, connection, thread, intuition.
        salience: Override initial salience (0.0-1.0). Auto-set by type if omitted.
        author: Who is thinking this (e.g., "human", "assistant", agent name).
        session_name: Session that created this item (for capture).
        item_id: Working memory item ID (required for get, resolve, pin, unpin, boost, archive).
        resolved_into: What the item crystallized into: memory, belief, work_item, decision, thinking_sequence.
        resolution_id: ID of the entity this resolved into.
        resolution_note: Context about the resolution.
        min_salience: Minimum salience filter for list (default 0.0).
        limit: Max results for list (default 20).
        offset: Pagination offset for list.
    """
    try:
        def _do_working_memory():
            # ca-173: Working memory is now unified into memories table.
            # All operations delegate to MemoryStore with salience-based lifecycle.
            if action == "capture":
                if not project or not content:
                    return {"error": "project and content are required for capture"}
                return memory_store.store(
                    content=content,
                    project=project,
                    memory_type=item_type or "thread",
                    salience=salience,
                    author=author,
                    session_name=session_name,
                )

            if action == "list":
                if not project:
                    return {"error": "project is required for list"}
                return memory_store.orient_items(project, limit=min(limit, MAX_LIMIT))

            if action == "get":
                if not item_id:
                    return {"error": "item_id is required for get"}
                results = memory_store.recall([item_id])
                return results[0] if results else {"error": f"Item {item_id} not found"}

            if action == "resolve":
                if not item_id:
                    return {"error": "item_id is required for resolve"}
                return memory_store.modify(item_id, action="graduate")

            if action == "pin":
                if not item_id:
                    return {"error": "item_id is required for pin"}
                return memory_store.modify(item_id, action="pin")

            if action == "unpin":
                if not item_id:
                    return {"error": "item_id is required for unpin"}
                return memory_store.modify(item_id, action="unpin")

            if action == "boost":
                if not item_id:
                    return {"error": "item_id is required for boost"}
                return memory_store.modify(item_id, action="boost")

            if action == "archive":
                if not item_id:
                    return {"error": "item_id is required for archive"}
                return memory_store.modify(item_id, action="inactivate", reason="archived via working_memory tool")

            return {"error": f"Unknown action: {action}"}

        return await _in_thread(_do_working_memory)
    except Exception as e:
        logger.exception("working_memory failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 16: drift_check
# ============================================================

@mcp.tool()
async def drift_check(
    project: str | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Check for memories with stale file references via content hash comparison.

    WHEN TO USE: Verify if stored memories about code/config files are still accurate.
    - Before relying on a stored memory about a specific file's contents
    - Periodic maintenance to find outdated code-snippet or decision memories
    - After major refactors to identify memories that need updating

    Pull-based: the caller computes and provides current file hashes because
    Cairn may run on a different host than the codebase. Returns memories where
    the referenced files have changed since the memory was stored.

    Args:
        project: Filter to a specific project. Omit to check all.
        files: List of {path: str, hash: str} — current file content hashes.
               Use sha256 or any consistent hash of file contents.
    """
    try:
        if drift_detector is None:
            return {"error": "drift detector not available"}
        return await _in_thread(drift_detector.check, project=project, files=files)
    except Exception as e:
        logger.exception("drift_check failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 16: ingest
# ============================================================

@mcp.tool()
async def ingest(
    content: str | None = None,
    project: str | None = None,
    url: str | None = None,
    hint: str = "auto",
    doc_type: str | None = None,
    title: str | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
    session_name: str | None = None,
    memory_type: str | None = None,
    file_path: str | None = None,
) -> dict:
    """Ingest content into Cairn: dedup, classify, chunk, and store.

    Smart ingestion pipeline that handles text, URLs, and local files. Content
    is classified as doc, memory, or both. Large content is automatically
    chunked. Duplicates are detected by content hash.

    WHEN TO USE:
    - Storing large documents (briefs, primers, plans) — pass the content directly
    - Importing web pages — pass a URL
    - Bulk loading content that needs to be chunked and indexed

    DON'T USE FOR: Quick notes or decisions — use store() instead.

    Args:
        content: Text content to ingest. Required unless url or file_path is provided.
        project: Project name. Required.
        url: URL to fetch and ingest. If content is also provided, url becomes source metadata.
        hint: Classification hint: 'auto' (LLM classifies), 'doc', 'memory', or 'both'.
        doc_type: Document type if storing as doc: 'brief', 'prd', 'plan', 'primer', 'writeup', 'guide'.
        title: Optional title for the document.
        source: Source attribution (auto-set to url if url provided).
        tags: Optional tags for memories created from chunks.
        session_name: Optional session grouping for memories.
        memory_type: Override memory type for chunks (default: 'note').
        file_path: Path to a local file in the server's ingest staging directory.
            Use this to ingest from the staging directory (e.g. after rsync or batch import).
            The file must be under the configured CAIRN_INGEST_DIR (default: /data/ingest).
    """
    try:
        if not content and not url and not file_path:
            return {"error": "content, url, or file_path is required"}
        if not project:
            return {"error": "project is required"}
        if hint not in ("auto", "doc", "memory", "both"):
            return {"error": "hint must be one of: auto, doc, memory, both"}

        def _do_ingest():
            return ingest_pipeline.ingest(
                content=content,
                project=project,
                url=url,
                hint=hint,
                doc_type=doc_type,
                title=title,
                source=source,
                tags=tags,
                session_name=session_name,
                memory_type=memory_type,
                file_path=file_path,
            )

        return await _in_thread(_do_ingest)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("ingest failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Code Intelligence (v0.58.0)
# ============================================================


@mcp.tool()
async def code_index(
    project: str,
    path: str,
    force: bool = False,
) -> dict:
    """Index a codebase for structural analysis. Parses source files with
    tree-sitter and stores the code graph (files, symbols, imports) in Neo4j.

    Per-project: each project gets its own code graph. Unchanged files are
    skipped via content-hash comparison. Safe to run repeatedly.

    WHEN TO USE:
    - First time analyzing a codebase: index the whole repo
    - After significant changes: re-index to update the code graph
    - Before running code_query or arch_check on a project

    Args:
        project: Project name to index under.
        path: Root directory to scan (absolute path).
        force: Re-index all files even if unchanged (default: False).
    """
    from cairn.core.code_ops import run_code_index

    try:
        return await _in_thread(
            run_code_index,
            project=project, path=path, force=force,
            graph_provider=graph_provider, db=db, config=config,
        )
    except Exception as e:
        logger.exception("code_index failed")
        return {"error": f"Internal error: {e}"}


@mcp.tool()
async def code_query(
    action: str,
    project: str,
    target: str = "",
    query: str = "",
    kind: str = "",
    depth: int = 3,
    limit: int = 20,
    mode: str = "fulltext",
) -> dict:
    """Query the code graph for structural information about an indexed project.

    Answers questions like "What depends on this file?", "What's the blast
    radius if I change this module?", and "What symbols are defined here?"

    Requires a prior ``code_index`` run to populate the graph.

    WHEN TO USE:
    - Understanding dependencies before making changes
    - Estimating impact/blast radius of a refactor
    - Exploring the structure of a file or module
    - Finding symbols by name across a project
    - Finding structurally important files (hotspots)
    - Discovering entity-code relationships
    - Searching across all indexed projects

    Actions:
    - ``dependents``: Files that import the target. "Who depends on me?"
    - ``dependencies``: Files the target imports. "What do I depend on?"
    - ``structure``: Symbols in the target file, hierarchically organized.
    - ``impact``: Transitive dependents — full blast radius up to *depth* hops.
    - ``search``: Search over symbol names (fulltext) or descriptions (semantic).
    - ``hotspots``: Top files by PageRank structural importance.
    - ``entities``: Knowledge entities linked to a code file.
    - ``code_for_entity``: Code files/symbols linked to a knowledge entity.
    - ``cross_search``: Search symbols across all indexed projects.
    - ``shared_deps``: Files that appear in multiple indexed projects.
    - ``bridge``: Create REFERENCED_IN edges between knowledge entities and code.

    Args:
        action: One of the actions listed above.
        project: Project name (must be indexed).
        target: File path or qualified symbol name (required for some actions).
        query: Search term (required for search/cross_search).
        kind: Filter symbols by kind: function, method, class, etc. (search only).
        depth: Max traversal depth for impact (default 3).
        limit: Max results (default 20).
        mode: Search mode: "fulltext" (default) or "semantic" (NL descriptions).
    """
    from cairn.core.code_ops import run_code_query

    try:
        return await _in_thread(
            run_code_query,
            action=action, project=project, target=target, query=query,
            kind=kind, depth=depth, limit=limit, mode=mode,
            graph_provider=graph_provider, db=db, config=config,
            embedding_engine=_svc.embedding if _svc else None,
        )
    except Exception as e:
        logger.exception("code_query failed")
        return {"error": f"Internal error: {e}"}


@mcp.tool()
async def code_describe(
    project: str,
    target: str = "",
    kind: str = "",
    limit: int = 50,
) -> dict:
    """Generate natural language descriptions for code symbols using LLM.

    Produces human-readable descriptions of what each symbol does, then
    embeds them for semantic search. Run this after ``code_index`` to enable
    ``code_query(action='search', mode='semantic')``.

    WHEN TO USE:
    - After indexing a codebase for the first time
    - After re-indexing to describe new/changed symbols
    - To enable natural language code search

    Args:
        project: Project name (must be indexed).
        target: File path to describe symbols in (describes all files if empty).
        kind: Filter by symbol kind (function, class, method, etc.).
        limit: Max symbols to describe (default 50).
    """
    from cairn.core.code_ops import run_code_describe

    try:
        return await _in_thread(
            run_code_describe,
            project=project, target=target, kind=kind, limit=limit,
            graph_provider=graph_provider, db=db, config=config,
            llm=_svc.llm if _svc else None, embedding_engine=_svc.embedding if _svc else None,
        )
    except Exception as e:
        logger.exception("code_describe failed")
        return {"error": f"Internal error: {e}"}


@mcp.tool()
async def arch_check(
    project: str,
    path: str = "",
    config_path: str = "",
    use_graph: bool = False,
) -> dict:
    """Check architecture boundary rules and integration contracts.

    Loads rules from a YAML file, a project doc (doc_type='architecture'),
    or the Neo4j code graph. Reports boundary violations and contract breaches.

    Rule sources (checked in order):
    1. ``config_path`` — explicit path to a YAML file
    2. Project doc — architecture doc stored via ``projects(action='create_doc', doc_type='architecture')``
    3. Error if neither is available

    Evaluation modes:
    - **Source** (default): re-parses Python files under ``path`` using stdlib ast.
      Supports both boundary rules and integration contracts.
    - **Graph** (``use_graph=True``): queries Neo4j IMPORTS edges. Faster for
      large codebases, but only evaluates boundary rules (contracts need
      name-level import info unavailable in file-level graph edges).

    WHEN TO USE:
    - Verify architecture boundaries before or after refactoring
    - CI-style checks on a project's codebase
    - Validate that modules only import declared public APIs (contracts)

    Args:
        project: Project name (for loading project-doc rules and graph queries).
        path: Source root directory (required for source-based evaluation).
        config_path: Explicit path to architecture YAML (overrides project doc).
        use_graph: Use Neo4j IMPORTS edges instead of re-parsing source (default: False).
    """
    from cairn.core.code_ops import run_arch_check

    try:
        return await _in_thread(
            run_arch_check,
            project=project, path=path, config_path=config_path,
            use_graph=use_graph,
            graph_provider=graph_provider, db=db, config=config,
            project_manager=project_manager,
        )
    except Exception as e:
        logger.exception("arch_check failed")
        return {"error": f"Internal error: {e}"}


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
                                    return await call_next(request)
                                logger.debug(
                                    "MCP: proxy header '%s' ignored — source %s not in TRUSTED_PROXY_IPS",
                                    _mcp_proxy_header, client_ip,
                                )
                            else:
                                return await call_next(request)

                    # Try API key fallback (legacy/simple auth)
                    if _mcp_api_key:
                        key = request.headers.get(_mcp_api_key_header)
                        if key and key == _mcp_api_key:
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
