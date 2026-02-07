"""Cairn MCP Server. Entry point for the semantic memory system."""

import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from cairn.config import load_config
from cairn.storage.database import Database
from cairn.embedding.engine import EmbeddingEngine
from cairn.core.memory import MemoryStore
from cairn.core.search import SearchEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cairn")

# Load configuration
config = load_config()

# Initialize components
db = Database(config.db)
embedding = EmbeddingEngine(config.embedding)
memory_store = MemoryStore(db, embedding)
search_engine = SearchEngine(db, embedding)


# ============================================================
# Lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Connect to database and run migrations on startup, clean up on shutdown."""
    db.connect()
    db.run_migrations()
    logger.info("Cairn started. Embedding model: %s", config.embedding.model)
    try:
        yield {}
    finally:
        db.close()
        logger.info("Cairn stopped.")


# Create MCP server
mcp = FastMCP(
    "cairn",
    instructions="Semantic memory for AI agents. Store, search, and discover patterns across persistent context.",
    lifespan=lifespan,
)


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
    return search_engine.search(
        query=query,
        project=project,
        memory_type=memory_type,
        search_mode=search_mode,
        limit=limit,
        include_full=include_full,
    )


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
    if len(ids) > 10:
        return {"error": "Maximum 10 IDs per recall. Batch into multiple calls."}
    return memory_store.recall(ids)


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
    return memory_store.modify(
        memory_id=id,
        action=action,
        content=content,
        memory_type=memory_type,
        importance=importance,
        tags=tags,
        reason=reason,
    )


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
    rows = db.execute(
        """
        SELECT m.id, m.content, m.importance, m.tags, m.created_at,
               p.name as project
        FROM memories m
        LEFT JOIN projects p ON m.project_id = p.id
        WHERE m.memory_type = 'rule'
            AND m.is_active = true
            AND (p.name = '__global__' OR p.name = %s)
        ORDER BY m.importance DESC, m.created_at DESC
        """,
        (project or "__global__",),
    )

    return [
        {
            "id": r["id"],
            "content": r["content"],
            "importance": r["importance"],
            "project": r["project"],
            "tags": r["tags"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


# ============================================================
# Tool 6: status
# ============================================================

@mcp.tool()
def status() -> dict:
    """System health and statistics.

    Returns memory count, project count, embedding model info, and database status.
    No parameters required.
    """
    memory_count = db.execute_one("SELECT COUNT(*) as count FROM memories WHERE is_active = true")
    project_count = db.execute_one("SELECT COUNT(*) as count FROM projects")
    type_counts = db.execute(
        """
        SELECT memory_type, COUNT(*) as count
        FROM memories WHERE is_active = true
        GROUP BY memory_type ORDER BY count DESC
        """
    )

    return {
        "status": "healthy",
        "memories": memory_count["count"],
        "projects": project_count["count"],
        "types": {r["memory_type"]: r["count"] for r in type_counts},
        "embedding_model": config.embedding.model,
        "embedding_dimensions": config.embedding.dimensions,
        "llm_backend": config.llm.backend,
        "llm_model": config.llm.bedrock_model if config.llm.backend == "bedrock" else config.llm.ollama_model,
    }


# ============================================================
# Entry point
# ============================================================

def main():
    """Run the Cairn MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
