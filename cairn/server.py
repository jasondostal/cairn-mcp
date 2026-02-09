"""Cairn MCP Server. Entry point for the semantic memory system."""

import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cairn.core.constants import (
    MAX_CAIRN_STACK, MAX_CONTENT_SIZE, MAX_LIMIT, MAX_NAME_LENGTH,
    MAX_RECALL_IDS, VALID_MEMORY_TYPES, VALID_SEARCH_MODES,
    CairnAction, MemoryAction,
)
from cairn.core.services import create_services
from cairn.core.status import get_status
from cairn.core.utils import ValidationError, validate_search, validate_store

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cairn")

# Initialize all services via factory
_svc = create_services()
config = _svc.config
db = _svc.db
memory_store = _svc.memory_store
search_engine = _svc.search_engine
cluster_engine = _svc.cluster_engine
project_manager = _svc.project_manager
task_manager = _svc.task_manager
thinking_engine = _svc.thinking_engine
session_synthesizer = _svc.session_synthesizer
consolidation_engine = _svc.consolidation_engine
cairn_manager = _svc.cairn_manager
digest_worker = _svc.digest_worker


# ============================================================
# Lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Connect to database and run migrations on startup, clean up on shutdown."""
    db.connect()
    db.run_migrations()
    digest_worker.start()
    logger.info("Cairn started. Embedding model: %s", config.embedding.model)
    try:
        yield {}
    finally:
        digest_worker.stop()
        db.close()
        logger.info("Cairn stopped.")


# Create MCP server
mcp_kwargs = dict(
    name="cairn",
    instructions="Semantic memory for AI agents. Store, search, and discover patterns across persistent context.",
    lifespan=lifespan,
)
if config.transport == "http":
    mcp_kwargs["host"] = config.http_host
    mcp_kwargs["port"] = config.http_port

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
) -> dict:
    """Store a memory with automatic embedding generation.

    Every memory is embedded as a vector for semantic search. Provide tags and
    importance to aid discovery, or let the system infer them (Phase 2 enrichment).

    Args:
        content: The memory content. Can be plain text, markdown, or code.
        project: Project name for organization. Use '__global__' for cross-project rules.
        memory_type: Classification. One of: note, decision, rule, code-snippet,
                     learning, research, discussion, progress, task, debug, design.
        importance: Priority score 0.0-1.0. Higher = more important.
        tags: Optional tags for categorization. Merged with auto-tags, not replaced.
        session_name: Optional session grouping (e.g., 'sprint-1', 'feature-auth').
        related_files: File paths related to this memory for code context searches.
        related_ids: IDs of related memories to link.
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
    """Search memories using hybrid semantic search.

    Combines three signals via Reciprocal Rank Fusion (RRF):
    - Vector similarity (60%): finds conceptually similar content
    - Keyword matching (25%): catches exact terms
    - Tag matching (15%): categorical filtering

    Use search_mode='keyword' for exact text matching or 'vector' for pure
    semantic similarity. Default 'semantic' mode uses all three signals.

    Args:
        query: Natural language search query.
        project: Filter to a specific project. Omit to search all.
        memory_type: Filter by type (e.g., 'decision', 'rule', 'code-snippet').
        search_mode: 'semantic' (hybrid RRF), 'keyword' (full-text), or 'vector' (embedding only).
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
    """Retrieve full content for specific memory IDs.

    Use after search to get complete details. Search returns summaries for
    context window efficiency; recall returns everything.

    Args:
        ids: List of memory IDs to retrieve (max 10 per call).
    """
    try:
        if not ids:
            return {"error": "ids list is required and cannot be empty"}
        if len(ids) > MAX_RECALL_IDS:
            return {"error": f"Maximum {MAX_RECALL_IDS} IDs per recall. Batch into multiple calls."}
        return memory_store.recall(ids)
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
) -> dict:
    """Update, soft-delete, or reactivate a memory.

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

    Returns rule-type memories from __global__ (universal guardrails) and
    the specified project. Rules guide agent behavior and are loaded at
    session start.

    Args:
        project: Project name to get rules for. Omit for global rules only.
    """
    try:
        result = memory_store.get_rules(project)
        return result["items"]
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

    Uses DBSCAN to group semantically similar memories into clusters, then
    generates labels and summaries for each cluster. Clustering runs lazily:
    only when stale (>24h, >20% growth, or first run).

    Args:
        project: Filter to a specific project. Omit for all projects.
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

        return {
            "status": "reclustered" if reclustered else "cached",
            "cluster_count": len(clusters),
            "clusters": clusters,
            "last_clustered_at": last_run["created_at"] if last_run else None,
        }
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
    target: str | None = None,
    link_type: str = "related",
) -> dict | list[dict]:
    """Manage projects, documents, and relationships.

    Actions:
    - 'list': List all projects with memory counts.
    - 'create_doc': Create a project document (brief, PRD, or plan).
    - 'get_docs': Get documents for a project, optionally filtered by type.
    - 'update_doc': Update an existing document's content.
    - 'link': Link two projects together.
    - 'get_links': Get all links for a project.

    Args:
        action: One of 'list', 'create_doc', 'get_docs', 'update_doc', 'link', 'get_links'.
        project: Project name (required for all actions except 'list').
        doc_type: Document type: 'brief', 'prd', or 'plan' (for create_doc, optional for get_docs).
        content: Document content (required for create_doc, update_doc).
        doc_id: Document ID (required for update_doc).
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
            return project_manager.create_doc(project, doc_type, content)

        if action == "get_docs":
            return project_manager.get_docs(project, doc_type=doc_type)

        if action == "update_doc":
            if not doc_id or not content:
                return {"error": "doc_id and content are required for update_doc"}
            return project_manager.update_doc(doc_id, content)

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
    """Manage tasks: create, complete, list, and link memories.

    Actions:
    - 'create': Create a new task.
    - 'complete': Mark a task as done.
    - 'list': List tasks for a project.
    - 'link_memories': Associate memories with a task.

    Args:
        action: One of 'create', 'complete', 'list', 'link_memories'.
        project: Project name.
        description: Task description (required for create).
        task_id: Task ID (required for complete, link_memories).
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

        return {"error": f"Unknown action: {action}"}
    except Exception as e:
        logger.exception("tasks failed")
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

    Use this for step-by-step reasoning, architecture decisions, or problem-solving.
    Start a sequence with a goal, add thoughts incrementally, then conclude.

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

    Returns memory count, project count, cluster info, embedding model info,
    and database status. No parameters required.
    """
    try:
        return get_status(db, config)
    except Exception as e:
        logger.exception("status failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 11: synthesize
# ============================================================

@mcp.tool()
def synthesize(
    project: str,
    session_name: str,
) -> dict:
    """Synthesize session memories into a coherent narrative.

    Fetches all memories for a session and uses LLM to create a narrative summary.
    Falls back to a structured list of memory summaries when LLM is unavailable.

    Args:
        project: Project name.
        session_name: Session identifier to synthesize.
    """
    try:
        if not project or not project.strip():
            return {"error": "project is required"}
        if not session_name or not session_name.strip():
            return {"error": "session_name is required"}
        return session_synthesizer.synthesize(project, session_name)
    except Exception as e:
        logger.exception("synthesize failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Tool 12: consolidate
# ============================================================

@mcp.tool()
def consolidate(
    project: str,
    dry_run: bool = True,
) -> dict:
    """Review project memories for duplicates and recommend consolidation actions.

    Finds semantically similar memory pairs (>0.85 cosine similarity), then asks LLM
    to recommend merges, promotions to rules, or inactivations. Dry run by default.

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
# Tool 13: cairns
# ============================================================

@mcp.tool()
def cairns(
    action: str,
    project: str | None = None,
    session_name: str | None = None,
    cairn_id: int | None = None,
    events: list | None = None,
    limit: int = 20,
) -> dict | list[dict]:
    """Set, view, and manage episodic session markers (cairns).

    A cairn marks the end of a session. It links all stones (memories) from that
    session into a navigable trail marker with an LLM-synthesized narrative.

    Actions:
    - 'set': Set a cairn at the end of a session. Links stones, synthesizes narrative.
    - 'stack': View the trail — cairns for a project, newest first.
    - 'get': Examine a single cairn with full detail and linked stones.
    - 'compress': Clear event detail, keep narrative. For storage management.

    Args:
        action: One of 'set', 'stack', 'get', 'compress'.
        project: Project name (required for set, stack).
        session_name: Session identifier (required for set). Must match memories' session_name.
        cairn_id: Cairn ID (required for get, compress).
        events: Optional ordered event log for set (from hooks). Stored as JSONB.
        limit: Maximum cairns to return for stack (default 20, max 50).
    """
    try:
        if action not in CairnAction.ALL:
            return {"error": f"invalid action: {action}. Must be one of: {', '.join(sorted(CairnAction.ALL))}"}

        if action == CairnAction.SET:
            if not project or not project.strip():
                return {"error": "project is required for set"}
            if not session_name or not session_name.strip():
                return {"error": "session_name is required for set"}
            if len(session_name) > MAX_NAME_LENGTH:
                return {"error": f"session_name exceeds {MAX_NAME_LENGTH} character limit"}
            return cairn_manager.set(project, session_name, events=events)

        if action == CairnAction.STACK:
            if not project or not project.strip():
                return {"error": "project is required for stack"}
            stack_limit = min(limit, MAX_CAIRN_STACK)
            return cairn_manager.stack(project, limit=stack_limit)

        if action == CairnAction.GET:
            if not cairn_id:
                return {"error": "cairn_id is required for get"}
            return cairn_manager.get(cairn_id)

        if action == CairnAction.COMPRESS:
            if not cairn_id:
                return {"error": "cairn_id is required for compress"}
            return cairn_manager.compress(cairn_id)

        return {"error": f"Unknown action: {action}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("cairns failed")
        return {"error": f"Internal error: {e}"}


# ============================================================
# Entry point
# ============================================================

def main():
    """Run the Cairn MCP server."""
    if config.transport == "http":
        import uvicorn
        from cairn.api import create_api

        # Get MCP's Starlette app (parent — owns lifespan, serves /mcp)
        mcp_app = mcp.streamable_http_app()

        # Wrap MCP's lifespan with DB lifecycle.
        # streamable_http_app() only starts the session manager — our custom
        # lifespan (DB connect) doesn't fire unless we inject it here.
        _mcp_lifespan = mcp_app.router.lifespan_context

        @asynccontextmanager
        async def combined_lifespan(app):
            db.connect()
            db.run_migrations()
            digest_worker.start()
            logger.info("Cairn started. Embedding: %s", config.embedding.model)
            try:
                async with _mcp_lifespan(app) as state:
                    yield state
            finally:
                digest_worker.stop()
                db.close()
                logger.info("Cairn stopped.")

        mcp_app.router.lifespan_context = combined_lifespan

        # Build REST API and mount as sub-app at /api
        api = create_api(_svc)
        mcp_app.mount("/api", api)

        logger.info("Starting Cairn (HTTP on %s:%d — MCP at /mcp, API at /api)", config.http_host, config.http_port)
        uvicorn.run(mcp_app, host=config.http_host, port=config.http_port)
    else:
        logger.info("Starting Cairn MCP server (stdio)")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
