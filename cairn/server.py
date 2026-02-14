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
graph_provider = _svc.graph_provider
memory_store = _svc.memory_store
search_engine = _svc.search_engine
search_v2_engine = _svc.search_v2
cluster_engine = _svc.cluster_engine
project_manager = _svc.project_manager
task_manager = _svc.task_manager
thinking_engine = _svc.thinking_engine
session_synthesizer = _svc.session_synthesizer
consolidation_engine = _svc.consolidation_engine
cairn_manager = _svc.cairn_manager
digest_worker = _svc.digest_worker
drift_detector = _svc.drift_detector
message_manager = _svc.message_manager
analytics_tracker = _svc.analytics_tracker
rollup_worker = _svc.rollup_worker


# ============================================================
# Lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Connect to database and run migrations on startup, clean up on shutdown."""
    db.connect()
    db.run_migrations()
    db.reconcile_vector_dimensions(config.embedding.dimensions)
    if graph_provider:
        try:
            graph_provider.connect()
            graph_provider.ensure_schema()
            logger.info("Neo4j graph connected and schema ensured")
        except Exception:
            logger.warning("Neo4j connection failed — graph features disabled", exc_info=True)
    digest_worker.start()
    if analytics_tracker:
        analytics_tracker.start()
    if rollup_worker:
        rollup_worker.start()
    logger.info("Cairn started. Embedding: %s (%d-dim)", config.embedding.backend, config.embedding.dimensions)
    try:
        yield {}
    finally:
        if rollup_worker:
            rollup_worker.stop()
        if analytics_tracker:
            analytics_tracker.stop()
        digest_worker.stop()
        if graph_provider:
            try:
                graph_provider.close()
            except Exception:
                pass
        db.close()
        logger.info("Cairn stopped.")


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
        "1. rules() — load behavioral guardrails (global + active project)\n"
        "2. cairns(action='stack') — walk recent session markers across all projects\n"
        "3. search(query='learning', memory_type='learning', limit=5) — surface recent learnings\n"
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
    - Every small step during a task (cairns handle session tracking)
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
        query: Natural language search query. Be specific — "deploy cairn UTIL" not just "deploy".
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

        # Use search_v2 when enabled (transparent swap)
        active_engine = search_v2_engine if search_v2_engine else search_engine
        results = active_engine.search(
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
    """Manage tasks: create, complete, list, and link memories.

    WHEN TO USE:
    - User explicitly requests: "remind me to...", "TODO:", "create a task for..."
    - Checking what's pending: "what tasks do we have", "what's outstanding"
    - Completing work: "mark that done", "finished that task"
    - Linking context: associate memories with a task for knowledge graph

    DON'T proactively create tasks unless the user asks. Tasks are user-requested
    follow-up items, not automatic tracking.

    Actions:
    - 'create': Create a new task.
    - 'complete': Mark a task as done.
    - 'list': List tasks for a project. Check at session start for pending work.
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
# Tool 11: synthesize
# ============================================================

@mcp.tool()
def synthesize(
    project: str,
    session_name: str,
) -> dict:
    """Synthesize session memories into a coherent narrative.

    WHEN TO USE: Session wrap-up — creating a narrative summary of what happened.
    Usually called before setting a cairn, or when reviewing past session work.

    PATTERN: synthesize (create narrative) → cairns(action='set') (mark session end)

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

    WHEN TO USE:
    - Session START: stack (view recent cairns across projects for orientation — step 2 of boot sequence)
    - Session END: set (mark session complete, link memories, generate narrative)
    - Context recovery: get (examine a specific past session in detail)

    PATTERN:
    - Boot: cairns(action='stack') → read recent trail markers
    - Wrap-up: synthesize() → cairns(action='set') → mark session end

    TRIGGER: "what did we do last time", "wrap up", "end of session", "set a cairn",
    "show me recent sessions", "what's the trail look like"

    Actions:
    - 'set': Set a cairn at the end of a session. Links stones, synthesizes narrative.
    - 'stack': View the trail — cairns for a project (or all projects), newest first.
    - 'get': Examine a single cairn with full detail and linked stones.
    - 'compress': Clear event detail, keep narrative. For storage management.

    Args:
        action: One of 'set', 'stack', 'get', 'compress'.
        project: Project name (required for set, optional for stack — omit for all projects).
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
            stack_limit = min(limit, MAX_CAIRN_STACK)
            proj = project.strip() if project and project.strip() else None
            return cairn_manager.stack(proj, limit=stack_limit)

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
# Tool 14: drift_check
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
# Tool 15: messages
# ============================================================

@mcp.tool()
def messages(
    action: str,
    project: str | None = None,
    content: str | None = None,
    sender: str | None = None,
    priority: str = "normal",
    message_id: int | None = None,
    include_archived: bool = False,
    limit: int = 20,
) -> dict | list[dict]:
    """Send and receive messages between agents and the user.

    WHEN TO USE:
    - Leaving a note for the user: task completed, issue found, question to answer later
    - Checking if anyone left you a message
    - Async communication between sessions

    Actions:
    - 'send': Send a message. Requires content and project.
    - 'inbox': Check messages. Optional project filter.
    - 'mark_read': Mark a message as read. Requires message_id.
    - 'mark_all_read': Mark all messages as read. Optional project filter.
    - 'archive': Archive a message. Requires message_id.
    - 'unread_count': Get count of unread messages. Optional project filter.

    Args:
        action: One of 'send', 'inbox', 'mark_read', 'mark_all_read', 'archive', 'unread_count'.
        project: Project name (required for send, optional filter for others).
        content: Message content (required for send).
        sender: Who is sending (default "assistant"). Any string — agent name, "user", etc.
        priority: "normal" or "urgent" (default "normal").
        message_id: Message ID (required for mark_read, archive).
        include_archived: Include archived messages in inbox (default false).
        limit: Max messages to return for inbox (default 20).
    """
    try:
        if action == "send":
            if not content:
                return {"error": "content is required for send"}
            if not project:
                return {"error": "project is required for send"}
            return message_manager.send(
                content=content,
                project=project,
                sender=sender or "assistant",
                priority=priority,
            )

        if action == "inbox":
            return message_manager.inbox(
                project=project,
                include_archived=include_archived,
                limit=min(limit, MAX_LIMIT),
            )["items"]

        if action == "mark_read":
            if not message_id:
                return {"error": "message_id is required for mark_read"}
            return message_manager.mark_read(message_id)

        if action == "mark_all_read":
            return message_manager.mark_all_read(project=project)

        if action == "archive":
            if not message_id:
                return {"error": "message_id is required for archive"}
            return message_manager.archive(message_id)

        if action == "unread_count":
            count = message_manager.unread_count(project=project)
            return {"count": count, "project": project}

        return {"error": f"Unknown action: {action}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("messages failed")
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
            db.reconcile_vector_dimensions(config.embedding.dimensions)
            if graph_provider:
                try:
                    graph_provider.connect()
                    graph_provider.ensure_schema()
                    logger.info("Neo4j graph connected and schema ensured")
                except Exception:
                    logger.warning("Neo4j connection failed — graph features disabled", exc_info=True)
            digest_worker.start()
            if analytics_tracker:
                analytics_tracker.start()
            if rollup_worker:
                rollup_worker.start()
            logger.info("Cairn started. Embedding: %s (%d-dim)", config.embedding.backend, config.embedding.dimensions)
            try:
                async with _mcp_lifespan(app) as state:
                    yield state
            finally:
                if rollup_worker:
                    rollup_worker.stop()
                if analytics_tracker:
                    analytics_tracker.stop()
                digest_worker.stop()
                if graph_provider:
                    try:
                        graph_provider.close()
                    except Exception:
                        pass
                db.close()
                logger.info("Cairn stopped.")

        mcp_app.router.lifespan_context = combined_lifespan

        # Build REST API and mount as sub-app at /api
        api = create_api(_svc)
        mcp_app.mount("/api", api)

        # Protect /mcp endpoint when auth is enabled.
        # The /api sub-app has its own APIKeyAuthMiddleware, so we only
        # guard MCP paths here. Health and status pass through.
        if config.auth.enabled and config.auth.api_key:
            from starlette.middleware.base import BaseHTTPMiddleware
            from starlette.responses import JSONResponse as StarletteJSONResponse

            class MCPAuthMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    path = request.url.path.rstrip("/")
                    # Only protect /mcp paths — /api has its own auth
                    if path.startswith("/mcp"):
                        if request.method == "OPTIONS":
                            return await call_next(request)
                        token = request.headers.get(config.auth.header_name)
                        if not token or token != config.auth.api_key:
                            return StarletteJSONResponse(
                                status_code=401,
                                content={"detail": "Invalid or missing API key"},
                            )
                    return await call_next(request)

            mcp_app.add_middleware(MCPAuthMiddleware)
            logger.info("MCP endpoint auth enabled (header: %s)", config.auth.header_name)

        logger.info("Starting Cairn (HTTP on %s:%d — MCP at /mcp, API at /api)", config.http_host, config.http_port)
        uvicorn.run(mcp_app, host=config.http_host, port=config.http_port)
    else:
        logger.info("Starting Cairn MCP server (stdio)")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
