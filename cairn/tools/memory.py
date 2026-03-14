"""Memory tools: store, search, recall, modify, ingest, consolidate."""

import logging

from cairn.core.services import Services
from cairn.core.tool_ops import budgeted_recall, budgeted_search, validate_modify_inputs
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.core.utils import ValidationError, validate_store
from cairn.tools.auth import check_project_access, require_admin
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register memory-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

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
            set_trace_tool("store")
            set_trace_project(project)
            check_project_access(svc, project)
            validate_store(content, project, memory_type, importance, tags, session_name)

            def _do_store():
                return svc.memory_store.store(
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

            return await in_thread(svc.db, _do_store)
        except ValidationError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("store failed")
            return {"error": f"Internal error: {e}"}

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
            set_trace_tool("search")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            def _do_search():
                raw = budgeted_search(
                    svc, query=query, project=project,
                    memory_type=memory_type, search_mode=search_mode,
                    limit=limit, include_full=include_full,
                    as_of=as_of, event_after=event_after,
                    event_before=event_before, ephemeral=ephemeral,
                )
                if "error" in raw:
                    return [raw]
                confidence = raw["confidence"]
                if confidence is not None:
                    return {"results": raw["results"], "confidence": confidence}
                return raw["results"]

            return await in_thread(svc.db, _do_search)
        except ValidationError as e:
            return [{"error": str(e)}]
        except Exception as e:
            logger.exception("search failed")
            return [{"error": f"Internal error: {e}"}]

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
            set_trace_tool("recall")
            def _do_recall():
                raw = budgeted_recall(svc, ids=ids)
                if "error" in raw:
                    return [raw]
                return raw["results"]

            return await in_thread(svc.db, _do_recall)
        except Exception as e:
            logger.exception("recall failed")
            return [{"error": f"Internal error: {e}"}]

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
            set_trace_tool("modify")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            err = validate_modify_inputs(action, content, memory_type, importance)
            if err:
                return {"error": err}

            def _do_modify():
                return svc.memory_store.modify(
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

            return await in_thread(svc.db, _do_modify)
        except Exception as e:
            logger.exception("modify failed")
            return {"error": f"Internal error: {e}"}

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
            set_trace_tool("ingest")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            if not content and not url and not file_path:
                return {"error": "content, url, or file_path is required"}
            if not project:
                return {"error": "project is required"}
            if hint not in ("auto", "doc", "memory", "both"):
                return {"error": "hint must be one of: auto, doc, memory, both"}

            def _do_ingest():
                return svc.ingest_pipeline.ingest(
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

            return await in_thread(svc.db, _do_ingest)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("ingest failed")
            return {"error": f"Internal error: {e}"}

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
            set_trace_tool("consolidate")
            if project:
                set_trace_project(project)
            require_admin(svc)
            check_project_access(svc, project)
            if not project or not project.strip():
                return {"error": "project is required"}
            if svc.consolidation_engine is None:
                return {"error": "consolidation engine not available"}
            if mode == "synthesize":
                return await in_thread(
                    svc.db,
                    svc.consolidation_engine.synthesize, project, dry_run=dry_run,
                    cluster_engine=svc.cluster_engine,
                    memory_store=svc.memory_store,
                    event_bus=svc.event_bus,
                    config=svc.config.consolidation_worker,
                )
            return await in_thread(
                svc.db,
                svc.consolidation_engine.consolidate, project, dry_run=dry_run,
            )
        except Exception as e:
            logger.exception("consolidate failed")
            return {"error": f"Internal error: {e}"}
