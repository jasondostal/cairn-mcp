"""Chat tool definitions and executor for agentic LLM chat."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from cairn.core.code_ops import run_arch_check, run_code_query
from cairn.core.status import get_status

if TYPE_CHECKING:
    from cairn.core.services import Services

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Cairn's built-in assistant. You have access to the user's semantic memory system — \
their stored knowledge, decisions, learnings, and project context.

Tone:
- Concise and direct. No filler, no fluff, no enthusiasm.
- Talk like a competent colleague, not a customer service bot.
- Don't narrate what you're about to do ("Let me search for that!"). Just do it.
- Don't repeat the user's question back to them.
- Short answers when short answers suffice. A few words > a paragraph.
- If the answer is in the tool results, just give the answer. Don't describe the tool call.

Tool use:
- Search first, guess never. If the user asks about something, check memories before answering.
- Use recent_activity when the user asks what's been happening, what we've been working on, \
or for general context. Don't just list projects — show what's actually going on.
- Use recall_memory when you need full content — search returns summaries.
- When storing memories, pick the right memory_type: note, decision, rule, code-snippet, \
learning, research, discussion, progress, task, debug, design.
- Use modify_memory to fix, update, or remove memories. Always search → recall → modify.
- Use discover_patterns when asked about patterns, trends, recurring themes, or what can be learned.
- Use think for collaborative reasoning — architecture decisions, debugging, multi-step analysis. \
Start a sequence, add thoughts, conclude when done.
- Use consolidate_memories when asked to clean up or deduplicate. Always dry_run first.
- Use ingest_content when the user wants to import content or a URL into the knowledge base.
- Use query_code and check_architecture for code structure questions — dependencies, hotspots, \
architecture validation. These require a project that has been indexed with code_index.
- Present results naturally. Summarize, don't dump.
"""

CHAT_TOOLS: list[dict] = [
    {
        "name": "recent_activity",
        "description": "Get recent activity across the memory system — what's been worked on, recent decisions, progress, and open work items. Use this when the user asks what's been happening, what we've been working on, or for general orientation.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter to a specific project (optional)"},
            },
        },
    },
    {
        "name": "search_memories",
        "description": "Search for memories using semantic search. Returns summaries of matching memories. Use recall_memory to get full content.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "project": {"type": "string", "description": "Filter by project name"},
                "memory_type": {"type": "string", "description": "Filter by type: note, decision, rule, learning, etc."},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Get the full content of specific memories by their IDs. Use after search to get details.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Memory IDs to retrieve (max 10)",
                },
            },
            "required": ["ids"],
        },
    },
    {
        "name": "store_memory",
        "description": "Store a new memory in the system.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The memory content"},
                "project": {"type": "string", "description": "Project to store under"},
                "memory_type": {
                    "type": "string",
                    "description": "Type: note, decision, rule, code-snippet, learning, research, discussion, progress, task, debug, design",
                },
                "importance": {"type": "number", "description": "Priority 0.0-1.0 (default 0.5)"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization",
                },
            },
            "required": ["content", "project"],
        },
    },
    {
        "name": "list_projects",
        "description": "List all projects in the memory system with their memory counts.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "system_status",
        "description": "Get Cairn system health, memory counts, and model information.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_rules",
        "description": "Get behavioral rules and guardrails. Returns rules for the specified project plus global rules.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name (also includes __global__ rules)"},
            },
        },
    },
    {
        "name": "list_tasks",
        "description": "List pending tasks for a project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name"},
                "include_completed": {"type": "boolean", "description": "Include completed tasks (default false)"},
            },
            "required": ["project"],
        },
    },
    {
        "name": "list_work_items",
        "description": "List work items for a project. Supports filtering by status, type, and assignee.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name"},
                "status": {"type": "string", "description": "Filter: open, ready, in_progress, blocked, done, cancelled"},
                "item_type": {"type": "string", "description": "Filter: epic, task, subtask"},
                "assignee": {"type": "string", "description": "Filter by assignee"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["project"],
        },
    },
    {
        "name": "create_work_item",
        "description": "Create a new work item (epic, task, or subtask).",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name"},
                "title": {"type": "string", "description": "Work item title"},
                "description": {"type": "string", "description": "Detailed description"},
                "item_type": {"type": "string", "description": "Type: epic, task, subtask (default task)"},
                "priority": {"type": "integer", "description": "Priority (higher = more urgent, default 0)"},
            },
            "required": ["project", "title"],
        },
    },
    {
        "name": "modify_memory",
        "description": "Update, soft-delete, or reactivate a memory. Use search → recall → modify pattern: find the memory first, verify it, then modify.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Memory ID to modify"},
                "action": {"type": "string", "description": "Action: update, inactivate, or reactivate"},
                "content": {"type": "string", "description": "New content (update only, triggers re-embedding)"},
                "memory_type": {"type": "string", "description": "New type classification (update only)"},
                "importance": {"type": "number", "description": "New importance 0.0-1.0 (update only)"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tags — replaces existing (update only)",
                },
                "reason": {"type": "string", "description": "Reason for inactivation (required for inactivate)"},
            },
            "required": ["id", "action"],
        },
    },
    {
        "name": "discover_patterns",
        "description": "Discover patterns across stored memories using semantic clustering. Use when asked about patterns, trends, recurring themes, common topics, or what can be learned from the memory base.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter to a specific project (optional, omit for cross-project)"},
                "topic": {"type": "string", "description": "Optional topic to filter clusters by relevance"},
                "limit": {"type": "integer", "description": "Max clusters to return (default 10)"},
            },
        },
    },
    {
        "name": "think",
        "description": "Structured thinking sequences for collaborative reasoning. Use for architecture decisions, debugging, multi-step analysis, or any problem that benefits from step-by-step reasoning. Actions: start (new sequence with a goal), add (add a thought), conclude (finalize), reopen (resume completed), get (retrieve full sequence), list (list sequences for project).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: start, add, conclude, reopen, get, list"},
                "project": {"type": "string", "description": "Project name"},
                "goal": {"type": "string", "description": "Problem or goal (required for start)"},
                "sequence_id": {"type": "integer", "description": "Sequence ID (required for add, conclude, reopen, get)"},
                "thought": {"type": "string", "description": "Thought content (required for add, conclude)"},
                "thought_type": {
                    "type": "string",
                    "description": "Type: observation, hypothesis, question, reasoning, conclusion, analysis, alternative, branch, insight, general",
                },
                "author": {"type": "string", "description": "Who contributed: human, assistant, or a name"},
            },
            "required": ["action", "project"],
        },
    },
    {
        "name": "consolidate_memories",
        "description": "Find duplicate or overlapping memories and recommend consolidation. Always runs as dry_run first to preview recommendations before applying changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project to consolidate"},
                "dry_run": {"type": "boolean", "description": "If true (default), only recommend. If false, apply changes."},
            },
            "required": ["project"],
        },
    },
    {
        "name": "ingest_content",
        "description": "Ingest content or a URL into the knowledge base. Handles dedup, classification, chunking, and storage. Use for importing documents, articles, or web pages. For quick notes, use store_memory instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project to ingest into"},
                "content": {"type": "string", "description": "Text content to ingest (required unless url provided)"},
                "url": {"type": "string", "description": "URL to fetch and ingest"},
                "title": {"type": "string", "description": "Optional title for the document"},
                "hint": {"type": "string", "description": "Classification: auto (default), doc, memory, or both"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for memories created from chunks",
                },
            },
            "required": ["project"],
        },
    },
    {
        "name": "query_code",
        "description": "Query the code graph for structural information about an indexed project. Actions: dependents (who depends on target), dependencies (what target depends on), structure (symbols in file), impact (blast radius), search (find symbols by name or description), hotspots (structurally important files), entities (knowledge entities linked to code), cross_search (search across all projects).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: dependents, dependencies, structure, impact, search, hotspots, entities, code_for_entity, cross_search, shared_deps, bridge"},
                "project": {"type": "string", "description": "Project name (must be indexed)"},
                "target": {"type": "string", "description": "File path or symbol name (required for dependents, dependencies, structure, impact, entities)"},
                "query": {"type": "string", "description": "Search term (required for search, cross_search)"},
                "depth": {"type": "integer", "description": "Max traversal depth for impact (default 3)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
                "mode": {"type": "string", "description": "Search mode: fulltext (default) or semantic"},
            },
            "required": ["action", "project"],
        },
    },
    {
        "name": "check_architecture",
        "description": "Check architecture boundary rules and integration contracts for an indexed project. Reports violations where modules import things they shouldn't. Requires an architecture doc stored for the project or a source path to scan.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name (must be indexed)"},
                "path": {"type": "string", "description": "Source root directory to scan (for source-based evaluation)"},
                "use_graph": {"type": "boolean", "description": "Use Neo4j graph instead of re-parsing source (default false)"},
            },
            "required": ["project"],
        },
    },
]


class ChatToolExecutor:
    """Executes chat tool calls against Cairn services."""

    def __init__(self, svc: "Services"):
        self.svc = svc

    def execute(self, name: str, input_data: dict) -> str:
        """Execute a tool call and return JSON result string."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = handler(**input_data)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.warning("Chat tool %s failed: %s", name, e, exc_info=True)
            return json.dumps({"error": str(e)})

    def _tool_recent_activity(self, project: str | None = None) -> dict:
        """Assemble recent context: recent memories, open work items, and trail."""
        sections: dict = {}

        # Recent memories (last ~10, sorted by recency)
        try:
            recent = self.svc.search_engine.search(
                query="recent progress decisions learnings",
                project=project, limit=10, include_full=False,
            )
            sections["recent_memories"] = [
                {
                    "id": r["id"],
                    "summary": r.get("summary") or r.get("content", "")[:200],
                    "memory_type": r.get("memory_type"),
                    "project": r.get("project"),
                    "importance": r.get("importance"),
                    "created_at": r.get("created_at"),
                }
                for r in recent
            ]
        except Exception:
            sections["recent_memories"] = []

        # Open work items
        try:
            if self.svc.work_item_manager:
                wi_result = self.svc.work_item_manager.list_items(
                    project=project, limit=10,
                )
                sections["open_work_items"] = [
                    {
                        "display_id": i["display_id"],
                        "title": i["title"],
                        "status": i["status"],
                        "item_type": i["item_type"],
                        "assignee": i.get("assignee"),
                        "project": i.get("project"),
                    }
                    for i in wi_result["items"]
                    if i["status"] not in ("done", "cancelled")
                ]
        except Exception:
            sections["open_work_items"] = []

        # Trail (recent graph activity)
        try:
            if self.svc.graph_provider:
                trail = self.svc.graph_provider.recent_activity(
                    project=project, limit=10,
                )
                sections["trail"] = trail
        except Exception:
            pass

        return sections

    def _tool_search_memories(
        self, query: str, project: str | None = None,
        memory_type: str | None = None, limit: int = 10,
    ) -> dict:
        results = self.svc.search_engine.search(
            query=query, project=project,
            memory_type=memory_type, limit=min(limit, 20),
            include_full=False,
        )
        return {
            "count": len(results),
            "results": [
                {
                    "id": r["id"],
                    "summary": r.get("summary") or r.get("content", "")[:200],
                    "memory_type": r.get("memory_type"),
                    "project": r.get("project"),
                    "importance": r.get("importance"),
                    "tags": r.get("tags", []),
                    "author": r.get("author"),
                    "score": round(r.get("score", 0), 3) if r.get("score") else None,
                    "created_at": r.get("created_at"),
                }
                for r in results
            ],
        }

    def _tool_recall_memory(self, ids: list[int]) -> dict:
        ids = ids[:10]
        results = self.svc.memory_store.recall(ids)
        return {
            "count": len(results),
            "memories": [
                {
                    "id": r["id"],
                    "content": r["content"],
                    "summary": r.get("summary"),
                    "memory_type": r.get("memory_type"),
                    "project": r.get("project"),
                    "importance": r.get("importance"),
                    "tags": r.get("tags", []),
                    "author": r.get("author"),
                    "is_active": r.get("is_active"),
                    "session_name": r.get("session_name"),
                    "created_at": r.get("created_at"),
                }
                for r in results
            ],
        }

    def _tool_store_memory(
        self, content: str, project: str, memory_type: str = "note",
        importance: float = 0.5, tags: list[str] | None = None,
    ) -> dict:
        result = self.svc.memory_store.store(
            content=content, project=project,
            memory_type=memory_type, importance=importance,
            tags=tags, author="assistant",
        )
        self.svc.db.commit()
        return {"stored": True, "id": result["id"], "project": project}

    def _tool_list_projects(self) -> dict:
        result = self.svc.project_manager.list_all()
        return {
            "count": result["total"],
            "projects": [
                {"name": p["name"], "memories": p["memory_count"], "created_at": p.get("created_at")}
                for p in result["items"]
            ],
        }

    def _tool_system_status(self) -> dict:
        return get_status(self.svc.db, self.svc.config)

    def _tool_get_rules(self, project: str | None = None) -> dict:
        result = self.svc.memory_store.get_rules(project=project)
        return {
            "count": result["total"],
            "rules": [
                {"id": r["id"], "content": r["content"], "importance": r["importance"], "project": r["project"]}
                for r in result["items"]
            ],
        }

    def _tool_list_tasks(self, project: str, include_completed: bool = False) -> dict:
        result = self.svc.task_manager.list_tasks(project=project, include_completed=include_completed)
        return {
            "count": result["total"],
            "tasks": [
                {"id": t["id"], "description": t["description"], "status": t["status"], "created_at": t.get("created_at")}
                for t in result["items"]
            ],
        }

    def _tool_list_work_items(
        self, project: str, status: str | None = None,
        item_type: str | None = None, assignee: str | None = None,
        limit: int = 20,
    ) -> dict:
        result = self.svc.work_item_manager.list_items(
            project=project, status=status, item_type=item_type,
            assignee=assignee, limit=min(limit, 50),
        )
        return {
            "count": result["total"],
            "items": [
                {
                    "id": i["id"],
                    "display_id": i["display_id"],
                    "title": i["title"],
                    "item_type": i["item_type"],
                    "priority": i["priority"],
                    "status": i["status"],
                    "assignee": i.get("assignee"),
                    "children_count": i.get("children_count", 0),
                    "created_at": i.get("created_at"),
                }
                for i in result["items"]
            ],
        }

    def _tool_create_work_item(
        self, project: str, title: str, description: str | None = None,
        item_type: str = "task", priority: int = 0,
    ) -> dict:
        result = self.svc.work_item_manager.create(
            project=project, title=title, description=description,
            item_type=item_type, priority=priority,
        )
        return {
            "created": True,
            "id": result["id"],
            "display_id": result["display_id"],
            "project": project,
            "title": title,
        }

    def _tool_modify_memory(
        self, id: int, action: str, content: str | None = None,
        memory_type: str | None = None, importance: float | None = None,
        tags: list[str] | None = None, reason: str | None = None,
    ) -> dict:
        if action not in ("update", "inactivate", "reactivate"):
            return {"error": f"invalid action: {action}. Must be: update, inactivate, reactivate"}
        result = self.svc.memory_store.modify(
            memory_id=id, action=action, content=content,
            memory_type=memory_type, importance=importance,
            tags=tags, reason=reason, author="assistant",
        )
        self.svc.db.commit()
        return result

    def _tool_discover_patterns(
        self, project: str | None = None, topic: str | None = None,
        limit: int = 10,
    ) -> dict:
        ce = self.svc.cluster_engine
        reclustered = False
        if ce.is_stale(project):
            ce.run_clustering(project)
            reclustered = True
        clusters = ce.get_clusters(
            project=project, topic=topic,
            min_confidence=0.5, limit=min(limit, 20),
        )
        last_run = ce.get_last_run(project)
        return {
            "status": "reclustered" if reclustered else "cached",
            "cluster_count": len(clusters),
            "clusters": clusters,
            "last_clustered_at": last_run["created_at"] if last_run else None,
        }

    def _tool_think(
        self, action: str, project: str, goal: str | None = None,
        sequence_id: int | None = None, thought: str | None = None,
        thought_type: str = "general", author: str | None = None,
    ) -> dict | list:
        te = self.svc.thinking_engine
        if action == "start":
            if not goal:
                return {"error": "goal is required for start"}
            return te.start(project, goal)
        if action == "add":
            if not sequence_id or not thought:
                return {"error": "sequence_id and thought are required for add"}
            return te.add_thought(sequence_id, thought, thought_type, None, author)
        if action == "conclude":
            if not sequence_id or not thought:
                return {"error": "sequence_id and thought are required for conclude"}
            return te.conclude(sequence_id, thought, author)
        if action == "reopen":
            if not sequence_id:
                return {"error": "sequence_id is required for reopen"}
            return te.reopen(sequence_id)
        if action == "get":
            if not sequence_id:
                return {"error": "sequence_id is required for get"}
            return te.get_sequence(sequence_id)
        if action == "list":
            return te.list_sequences(project)["items"]
        return {"error": f"Unknown action: {action}"}

    def _tool_consolidate_memories(
        self, project: str, dry_run: bool = True,
    ) -> dict:
        return self.svc.consolidation_engine.consolidate(project, dry_run=dry_run)

    def _tool_ingest_content(
        self, project: str, content: str | None = None,
        url: str | None = None, title: str | None = None,
        hint: str = "auto", tags: list[str] | None = None,
    ) -> dict:
        if not content and not url:
            return {"error": "content or url is required"}
        if hint not in ("auto", "doc", "memory", "both"):
            return {"error": "hint must be one of: auto, doc, memory, both"}
        return self.svc.ingest_pipeline.ingest(
            content=content, project=project, url=url,
            hint=hint, title=title, tags=tags,
        )

    def _tool_query_code(
        self, action: str, project: str, target: str = "",
        query: str = "", depth: int = 3, limit: int = 20,
        mode: str = "fulltext",
    ) -> dict:
        if not self.svc.graph_provider:
            return {"error": "Code intelligence requires Neo4j — not configured"}
        return run_code_query(
            action=action, project=project, target=target,
            query=query, kind="", depth=depth, limit=limit, mode=mode,
            graph_provider=self.svc.graph_provider, db=self.svc.db,
            config=self.svc.config, embedding_engine=self.svc.embedding,
        )

    def _tool_check_architecture(
        self, project: str, path: str = "", use_graph: bool = False,
    ) -> dict:
        if not self.svc.graph_provider:
            return {"error": "Code intelligence requires Neo4j — not configured"}
        return run_arch_check(
            project=project, path=path, config_path="",
            use_graph=use_graph, graph_provider=self.svc.graph_provider,
            db=self.svc.db, config=self.svc.config,
            project_manager=self.svc.project_manager,
        )
