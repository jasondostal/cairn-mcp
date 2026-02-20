"""Cairn MCP Server. Entry point for the semantic memory system."""

import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cairn.config import apply_overrides, load_config
from cairn.core.budget import apply_list_budget, truncate_to_budget
from cairn.core.constants import (
    BUDGET_INSIGHTS_PER_ITEM,
    BUDGET_RECALL_PER_ITEM, BUDGET_RULES_PER_ITEM, BUDGET_SEARCH_PER_ITEM,
    MAX_CONTENT_SIZE, MAX_LIMIT, MAX_NAME_LENGTH,
    MAX_RECALL_IDS, VALID_MEMORY_TYPES, VALID_SEARCH_MODES,
    ORIENT_ALLOC_RULES, ORIENT_ALLOC_LEARNINGS,
    ORIENT_ALLOC_TRAIL, ORIENT_ALLOC_WORK_ITEMS,
    ActivityType, MemoryAction,
)
from cairn.core.services import create_services
from cairn.core.status import get_status
from cairn.core.utils import ValidationError, validate_search, validate_store
from cairn.storage.database import Database
from cairn.storage import settings_store

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
analytics_tracker = None
rollup_worker = None
workspace_manager = None
ingest_pipeline = None


def _init_services(svc):
    """Assign module globals from a Services instance."""
    global _svc, config, db, graph_provider, memory_store, search_engine
    global cluster_engine, project_manager, task_manager
    global thinking_engine, session_synthesizer, consolidation_engine
    global event_bus, event_dispatcher, drift_detector
    global work_item_manager
    global analytics_tracker, rollup_worker, workspace_manager
    global ingest_pipeline

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
    logger.info("Cairn started. Embedding: %s (%d-dim)", cfg.embedding.backend, cfg.embedding.dimensions)


def _stop_workers(svc, db_instance):
    """Stop background workers and close connections."""
    if svc.event_dispatcher:
        svc.event_dispatcher.stop()
    if svc.rollup_worker:
        svc.rollup_worker.stop()
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
    """Connect to database, load overrides, create services, and run lifecycle."""
    db_instance = Database(_base_config.db)
    db_instance.connect()
    db_instance.run_migrations()

    final_config = _build_config_with_overrides(db_instance)
    svc = create_services(config=final_config, db=db_instance)
    _init_services(svc)

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
        "STORE THOUGHTFULLY: Consolidate, don't fragment. One comprehensive memory after a task "
        "completes is better than five incremental notes during it."
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
def store(
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
) -> dict:
    """Store a memory with automatic embedding generation and optional LLM enrichment.

    WHEN TO STORE — Consolidate, Don't Fragment:
    - Task/feature COMPLETE — capture the full journey (investigation → solution)
    - Discussion CONCLUDES — consolidate decisions and learnings into one memory
    - User explicitly says "remember this", "save this", "store this"
    - Context switch — save state before moving to a different topic
    - Key decision made — architecture choices, tool selections, process changes
    - Learning discovered — something that should persist across sessions

    DON'T STORE:
    - Every small step during a task (wait for completion)
    - Mid-conversation thoughts (wait for conclusions)
    - Incremental progress updates (one summary at the end is better)
    - Duplicate information already stored (search first!)

    ONE comprehensive memory > multiple fragments.

    MEMORY TYPES: note, decision, rule, code-snippet, learning, research,
    discussion, progress, task, debug, design.
    Use 'rule' for behavioral guardrails. Use '__global__' project for cross-project rules.

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
    """
    try:
        validate_store(content, project, memory_type, importance, tags, session_name)
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
        )
    except ValidationError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("store failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 2: search
# ============================================================

@mcp.tool()
def search(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    search_mode: str = "semantic",
    limit: int = 10,
    include_full: bool = False,
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
    """
    try:
        validate_search(query, limit)
        if search_mode not in VALID_SEARCH_MODES:
            return {"error": f"invalid search_mode: {search_mode}. Must be one of: {', '.join(VALID_SEARCH_MODES)}"}

        results = search_engine.search(
            query=query,
            project=project,
            memory_type=memory_type,
            search_mode=search_mode,
            limit=limit,
            include_full=include_full,
        )

        # Apply budget cap
        budget = config.budget.search
        if budget > 0 and results:
            content_key = "content" if include_full else "summary"
            results, meta = apply_list_budget(
                results, budget, content_key,
                per_item_max=BUDGET_SEARCH_PER_ITEM,
                overflow_message=(
                    "...{omitted} more results omitted. "
                    "Use recall(ids=[...]) for full content, or narrow your query."
                ),
            )
            if meta["omitted"] > 0:
                results.append({"_overflow": meta["overflow_message"]})

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
    except ValidationError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("search failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 3: recall
# ============================================================

@mcp.tool()
def recall(ids: list[int]) -> list[dict]:
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
            return {"error": "ids list is required and cannot be empty"}
        if len(ids) > MAX_RECALL_IDS:
            return {"error": f"Maximum {MAX_RECALL_IDS} IDs per recall. Batch into multiple calls."}
        results = memory_store.recall(ids)

        # Apply budget cap
        budget = config.budget.recall
        if budget > 0 and results:
            results, meta = apply_list_budget(
                results, budget, "content",
                per_item_max=BUDGET_RECALL_PER_ITEM,
                overflow_message=(
                    "...{omitted} memories truncated from response. "
                    "Recall fewer IDs per call for full content."
                ),
            )
            if meta["omitted"] > 0:
                results.append({"_overflow": meta["overflow_message"]})
        return results
    except Exception as e:
        logger.exception("recall failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 4: modify
# ============================================================

@mcp.tool()
def modify(
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
    except Exception as e:
        logger.exception("modify failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 5: rules
# ============================================================

@mcp.tool()
def rules(project: str | None = None) -> list[dict]:
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
    except Exception as e:
        logger.exception("rules failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 6: insights
# ============================================================

@mcp.tool()
def insights(
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
        # Check staleness and recluster if needed
        reclustered = False
        if cluster_engine.is_stale(project):
            cluster_engine.run_clustering(project)
            reclustered = True

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
        if overflow_msg:
            result["_overflow"] = overflow_msg
        return result
    except Exception as e:
        logger.exception("insights failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 7: projects
# ============================================================

@mcp.tool()
def projects(
    action: str,
    project: str | None = None,
    doc_type: str | None = None,
    content: str | None = None,
    doc_id: int | None = None,
    title: str | None = None,
    target: str | None = None,
    link_type: str = "related",
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
        content: Document content (required for create_doc, update_doc).
        doc_id: Document ID (required for update_doc).
        title: Optional document title (for create_doc, update_doc).
        target: Target project name (required for link).
        link_type: Relationship type for link (default 'related').
    """
    try:
        if action == "list":
            return project_manager.list_all()["items"]

        if not project:
            return {"error": "project is required for this action"}

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
    except Exception as e:
        logger.exception("projects failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 8: tasks
# ============================================================

@mcp.tool()
def tasks(
    action: str,
    project: str,
    description: str | None = None,
    task_id: int | None = None,
    memory_ids: list[int] | None = None,
    include_completed: bool = False,
) -> dict | list[dict]:
    """Personal reminders and TODO items — human-only quick capture.

    This is the HUMAN-ONLY quick-capture tool. Tasks here are personal reminders
    ("buy milk", "review PR #42", "schedule dentist") that should NEVER appear
    in the agent dispatch queue. Agents do not claim, execute, or heartbeat on
    these items.

    For structured, dispatchable work that agents and humans collaborate on,
    use work_items() instead.

    WHEN TO USE:
    - User explicitly requests: "remind me to...", "TODO:", "create a task for..."
    - Checking what's pending: "what tasks do we have", "what's outstanding"
    - Completing work: "mark that done", "finished that task"
    - Promoting a reminder to real work: "make this a work item"

    DON'T proactively create tasks unless the user asks. Tasks are user-requested
    reminders, not automatic tracking.

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
    except Exception as e:
        logger.exception("tasks failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 17: work_items
# ============================================================

@mcp.tool()
def work_items(
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
    - 'gated': Items awaiting gates. Optional: project, gate_type.
    """
    try:
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
            return work_item_manager.complete(work_item_id, session_name=session_name)

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

        if action == "gated":
            return work_item_manager.gated_items(
                project=project, gate_type=gate_type, limit=min(limit, MAX_LIMIT),
            )

        return {"error": f"Unknown action: {action}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("work_items failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 9: think
# ============================================================

@mcp.tool()
def think(
    action: str,
    project: str,
    goal: str | None = None,
    sequence_id: int | None = None,
    thought: str | None = None,
    thought_type: str = "general",
    branch_name: str | None = None,
) -> dict | list[dict]:
    """Structured thinking sequences for complex reasoning.

    TRIGGER: When a problem has multiple valid approaches or needs step-by-step analysis:
    - "think through", "analyze", "reason about", "let's consider"
    - Architecture decisions with trade-offs
    - Debugging complex issues (hypothesis → test → observe → conclude)
    - Planning multi-step implementations
    - Any problem where the user wants to participate in the reasoning

    PATTERN: start (with goal) → add thoughts (observations, hypotheses, analysis) → conclude
    Use 'alternative' or 'branch' thought_type to explore divergent paths.

    WHEN NOT TO USE: Simple questions (use search), straightforward tasks, quick lookups.

    Actions:
    - 'start': Begin a new thinking sequence with a goal.
    - 'add': Add a thought to an active sequence.
    - 'conclude': Finalize a sequence with a conclusion.
    - 'get': Retrieve a full sequence with all thoughts.
    - 'list': List thinking sequences for a project.

    Args:
        action: One of 'start', 'add', 'conclude', 'get', 'list'.
        project: Project name.
        goal: The problem or goal (required for start).
        sequence_id: Sequence ID (required for add, conclude, get).
        thought: The thought content (required for add, conclude).
        thought_type: Type: observation, hypothesis, question, reasoning, conclusion,
                      assumption, analysis, general, alternative, branch.
        branch_name: Name for a branch when thought_type is alternative/branch.
    """
    try:
        if action == "start":
            if not goal:
                return {"error": "goal is required for start"}
            return thinking_engine.start(project, goal)

        if action == "add":
            if not sequence_id or not thought:
                return {"error": "sequence_id and thought are required for add"}
            return thinking_engine.add_thought(sequence_id, thought, thought_type, branch_name)

        if action == "conclude":
            if not sequence_id or not thought:
                return {"error": "sequence_id and thought (conclusion) are required for conclude"}
            return thinking_engine.conclude(sequence_id, thought)

        if action == "get":
            if not sequence_id:
                return {"error": "sequence_id is required for get"}
            return thinking_engine.get_sequence(sequence_id)

        if action == "list":
            return thinking_engine.list_sequences(project)["items"]

        return {"error": f"Unknown action: {action}"}
    except Exception as e:
        logger.exception("think failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 10: status
# ============================================================

@mcp.tool()
def status() -> dict:
    """System health and statistics.

    WHEN TO USE: Health checks, system overview, "how many memories", "is cairn working",
    verifying deployment status. Quick diagnostic tool — no parameters required.
    """
    try:
        return get_status(db, config)
    except Exception as e:
        logger.exception("status failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool: consolidate
# ============================================================

@mcp.tool()
def consolidate(
    project: str,
    dry_run: bool = True,
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
    """
    try:
        if not project or not project.strip():
            return {"error": "project is required"}
        return consolidation_engine.consolidate(project, dry_run=dry_run)
    except Exception as e:
        logger.exception("consolidate failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Trail helper (shared by trail() and orient())
# ============================================================

def _fetch_trail_data(
    project: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> dict:
    """Fetch recent activity trail data. Used by both trail() and orient().

    Returns structured dict with source, since, and sessions.
    Tries graph-based trail first, falls back to memory query.
    """
    from datetime import datetime, timedelta, timezone

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    project_id = None
    if project:
        from cairn.core.utils import get_project
        project_id = get_project(db, project)

    # Try graph-based trail first
    if graph_provider:
        try:
            activity = graph_provider.recent_activity(
                project_id=project_id, since=since, limit=limit,
            )
            if activity:
                episode_ids = list({a["episode_id"] for a in activity if a.get("episode_id")})
                session_map = {}
                if episode_ids:
                    placeholders = ",".join(["%s"] * len(episode_ids))
                    rows = db.execute(
                        f"SELECT id, session_name FROM memories WHERE id IN ({placeholders})",
                        tuple(episode_ids),
                    )
                    session_map = {r["id"]: r["session_name"] for r in rows}

                sessions: dict[str, dict] = {}
                for a in activity:
                    session_name = session_map.get(a.get("episode_id"), "unknown")
                    if session_name not in sessions:
                        sessions[session_name] = {
                            "session_name": session_name,
                            "entities_touched": set(),
                            "key_facts": [],
                            "time_range": {"earliest": a.get("created_at"), "latest": a.get("created_at")},
                        }
                    s = sessions[session_name]
                    if a.get("subject_name"):
                        s["entities_touched"].add(a["subject_name"])
                    if a.get("object_name"):
                        s["entities_touched"].add(a["object_name"])
                    if len(s["key_facts"]) < 5:
                        s["key_facts"].append(a.get("fact", ""))
                    ts = a.get("created_at")
                    if ts:
                        if not s["time_range"]["earliest"] or ts < s["time_range"]["earliest"]:
                            s["time_range"]["earliest"] = ts
                        if not s["time_range"]["latest"] or ts > s["time_range"]["latest"]:
                            s["time_range"]["latest"] = ts

                session_list = []
                for s in sessions.values():
                    s["entities_touched"] = sorted(s["entities_touched"])
                    session_list.append(s)

                result = {
                    "source": "graph",
                    "since": since,
                    "sessions": session_list[:10],
                }

                # Include thinking activity if available
                try:
                    thinking_activity = graph_provider.recent_thinking_activity(
                        project_id=project_id, since=since, limit=10,
                    )
                    if thinking_activity:
                        result["thinking"] = [
                            {
                                "type": "thinking",
                                "goal": t.get("goal", ""),
                                "status": t.get("status", ""),
                                "thought_count": t.get("thought_count", 0),
                                "created_at": t.get("created_at", ""),
                            }
                            for t in thinking_activity
                        ]
                except Exception:
                    logger.debug("Thinking trail failed", exc_info=True)

                return result
        except Exception:
            logger.debug("Graph trail failed, falling back to memory query", exc_info=True)

    # Fallback: simple memory query
    rows = db.execute(
        """
        SELECT m.session_name, m.memory_type, m.summary,
               m.created_at, p.name AS project
        FROM memories m
        LEFT JOIN projects p ON m.project_id = p.id
        WHERE m.is_active = true AND m.created_at > %s
        """
        + (" AND m.project_id = %s" if project_id else "")
        + " ORDER BY m.created_at DESC LIMIT %s",
        (since,) + ((project_id,) if project_id else ()) + (limit,),
    )

    sessions_fallback: dict[str, list] = {}
    for r in rows:
        sn = r["session_name"] or "no-session"
        sessions_fallback.setdefault(sn, []).append({
            "type": r["memory_type"],
            "summary": r["summary"] or "",
            "project": r["project"],
        })

    return {
        "source": "memory",
        "since": since,
        "sessions": [
            {"session_name": sn, "memories": mems[:5]}
            for sn, mems in list(sessions_fallback.items())[:10]
        ],
    }


# ============================================================
# Tool: orient
# ============================================================

@mcp.tool()
def orient(project: str | None = None) -> dict:
    """Single-pass session boot. Returns rules, trail, learnings, and work items.

    Replaces calling rules() + search() + work_items() individually with one call.
    Each section gets a token budget allocation with surplus flowing to the next.

    Use this at session start. Individual tools remain available for granular
    use mid-session.

    Args:
        project: Project name for scoped rules and work items. Omit for global-only boot.
    """
    from cairn.core.budget import apply_list_budget, estimate_tokens_for_dict

    try:
        total_budget = config.budget.orient
        budget_rules = int(total_budget * ORIENT_ALLOC_RULES)
        budget_learnings = int(total_budget * ORIENT_ALLOC_LEARNINGS)
        budget_trail = int(total_budget * ORIENT_ALLOC_TRAIL)
        budget_work_items = int(total_budget * ORIENT_ALLOC_WORK_ITEMS)

        tokens_used = 0

        # --- Section 1: Rules (30%) ---
        rules_data = []
        try:
            result = memory_store.get_rules(project)
            rules_items = result.get("items", [])
            if rules_items:
                rules_data, rules_meta = apply_list_budget(
                    rules_items, budget_rules, "content",
                    per_item_max=BUDGET_RULES_PER_ITEM,
                    overflow_message="...{omitted} more rules omitted.",
                )
                if rules_meta["omitted"] > 0:
                    rules_data.append({"_overflow": rules_meta["overflow_message"]})
                rules_tokens = estimate_tokens_for_dict(rules_data)
                tokens_used += rules_tokens
                surplus = max(0, budget_rules - rules_tokens)
            else:
                surplus = budget_rules
            budget_learnings += surplus
        except Exception:
            logger.debug("orient: rules section failed", exc_info=True)
            budget_learnings += budget_rules

        # --- Section 2: Learnings (25% + surplus) ---
        learnings_data = []
        try:
            learnings_results = search_engine.search(
                query="learning",
                project=project,
                memory_type="learning",
                search_mode="semantic",
                limit=5,
                include_full=True,
            )
            if learnings_results:
                learnings_data, learnings_meta = apply_list_budget(
                    learnings_results, budget_learnings, "content",
                    per_item_max=BUDGET_SEARCH_PER_ITEM,
                    overflow_message="...{omitted} more learnings omitted.",
                )
                if learnings_meta["omitted"] > 0:
                    learnings_data.append({"_overflow": learnings_meta["overflow_message"]})
                learnings_tokens = estimate_tokens_for_dict(learnings_data)
                tokens_used += learnings_tokens
                surplus = max(0, budget_learnings - learnings_tokens)
            else:
                surplus = budget_learnings
            budget_trail += surplus
        except Exception:
            logger.debug("orient: learnings section failed", exc_info=True)
            budget_trail += budget_learnings

        # --- Section 3: Trail (25% + surplus) ---
        trail_data = {}
        try:
            trail_data = _fetch_trail_data(project=project, limit=20)
            trail_tokens = estimate_tokens_for_dict(trail_data)
            # Trim if over budget
            if budget_trail > 0 and trail_tokens > budget_trail:
                for s in trail_data.get("sessions", []):
                    if "key_facts" in s:
                        s["key_facts"] = s["key_facts"][:3]
                trail_data["sessions"] = trail_data.get("sessions", [])[:5]
                trail_tokens = estimate_tokens_for_dict(trail_data)
            tokens_used += trail_tokens
            surplus = max(0, budget_trail - trail_tokens)
            budget_work_items += surplus
        except Exception:
            logger.debug("orient: trail section failed", exc_info=True)
            budget_work_items += budget_trail

        # --- Section 4: Work Items (20% + surplus) ---
        # Try work items first; fall back to flat tasks if none exist
        work_items_data = []
        try:
            if project:
                # Work items: ready queue + active (in_progress) items
                wi_ready = work_item_manager.ready_queue(project, limit=10)
                wi_active = work_item_manager.list_items(
                    project=project, status="in_progress", limit=10,
                )
                wi_items = []
                for item in wi_ready.get("items", []):
                    wi_items.append({
                        "short_id": item.get("short_id", ""),
                        "title": item.get("title", ""),
                        "priority": item.get("priority", 0),
                        "item_type": item.get("item_type", "task"),
                        "status": "ready",
                    })
                for item in wi_active.get("items", []):
                    wi_items.append({
                        "short_id": item.get("short_id", ""),
                        "title": item.get("title", ""),
                        "assignee": item.get("assignee"),
                        "item_type": item.get("item_type", "task"),
                        "status": "in_progress",
                    })
                if wi_items:
                    work_items_data = wi_items
                else:
                    # Fall back to flat tasks
                    tasks_result = task_manager.list_tasks(project, include_completed=False)
                    work_items_data = tasks_result.get("items", [])
            if work_items_data:
                content_key = "title" if work_items_data and "title" in work_items_data[0] else "description"
                work_items_data, wi_meta = apply_list_budget(
                    work_items_data, budget_work_items, content_key,
                    overflow_message="...{omitted} more work items omitted.",
                )
                if wi_meta["omitted"] > 0:
                    work_items_data.append({"_overflow": wi_meta["overflow_message"]})
                tokens_used += estimate_tokens_for_dict(work_items_data)
        except Exception:
            logger.debug("orient: work items section failed", exc_info=True)

        return {
            "project": project,
            "rules": rules_data,
            "trail": trail_data,
            "learnings": learnings_data,
            "work_items": work_items_data,
            "_budget": {"total": total_budget, "used": tokens_used},
        }
    except Exception as e:
        logger.exception("orient failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 15: drift_check
# ============================================================

@mcp.tool()
def drift_check(
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
        return drift_detector.check(project=project, files=files)
    except Exception as e:
        logger.exception("drift_check failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 16: ingest
# ============================================================

@mcp.tool()
def ingest(
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
) -> dict:
    """Ingest content into Cairn: dedup, classify, chunk, and store.

    Smart ingestion pipeline that handles text and URLs. Content is classified
    as doc, memory, or both. Large content is automatically chunked. Duplicates
    are detected by content hash.

    WHEN TO USE:
    - Importing documents, articles, or web pages into the knowledge base
    - Bulk loading content that needs to be chunked and indexed
    - Ingesting URLs (fetches, extracts readable text, stores)

    DON'T USE FOR: Quick notes or decisions — use store() instead.

    Args:
        content: Text content to ingest. Required unless url is provided.
        project: Project name. Required.
        url: URL to fetch and ingest. If content is also provided, url becomes source metadata.
        hint: Classification hint: 'auto' (LLM classifies), 'doc', 'memory', or 'both'.
        doc_type: Document type if storing as doc: 'brief', 'prd', 'plan', 'primer', 'writeup', 'guide'.
        title: Optional title for the document.
        source: Source attribution (auto-set to url if url provided).
        tags: Optional tags for memories created from chunks.
        session_name: Optional session grouping for memories.
        memory_type: Override memory type for chunks (default: 'note').
    """
    try:
        if not content and not url:
            return {"error": "content or url is required"}
        if not project:
            return {"error": "project is required"}
        if hint not in ("auto", "doc", "memory", "both"):
            return {"error": "hint must be one of: auto, doc, memory, both"}

        result = ingest_pipeline.ingest(
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
        )
        return result
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("ingest failed")
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


        @asynccontextmanager
        async def combined_lifespan(app):
            _start_workers(svc, final_config, db_instance)
            try:
                async with _mcp_lifespan(app) as state:
                    yield state
            finally:
                _stop_workers(svc, db_instance)

        mcp_app.router.lifespan_context = combined_lifespan

        logger.info("Starting Cairn (HTTP on %s:%d — MCP at /mcp, API at /api)", _base_config.http_host, _base_config.http_port)
        uvicorn.run(mcp_app, host=_base_config.http_host, port=_base_config.http_port)
    else:
        logger.info("Starting Cairn MCP server (stdio)")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
