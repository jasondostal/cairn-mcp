"""Chat tool definitions and executor for agentic LLM chat."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

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
- Present results naturally. Summarize, don't dump.
- send_message is for async notes only — things the user should see later, not right now.
  Do NOT use it during normal conversation. If the user is chatting with you, just respond in chat.
  Only send_message when: flagging something discovered during a search that's unrelated to the
  current conversation, or leaving a reminder the user asked you to leave.
- check_inbox is for checking messages from other agents, not for regular conversation.
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
        "name": "send_message",
        "description": "Send a message to the user or leave a note for other agents. Use for flagging things, leaving reminders, or async communication.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The message content"},
                "project": {"type": "string", "description": "Project to associate with"},
                "priority": {"type": "string", "description": "Priority: 'normal' or 'urgent' (default normal)"},
            },
            "required": ["content", "project"],
        },
    },
    {
        "name": "check_inbox",
        "description": "Check for unread messages from other agents or the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project (optional)"},
                "limit": {"type": "integer", "description": "Max messages to return (default 10)"},
            },
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
                        "short_id": i["short_id"],
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

    def _tool_send_message(self, content: str, project: str, priority: str = "normal") -> dict:
        result = self.svc.message_manager.send(
            content=content, project=project,
            sender="assistant", priority=priority,
        )
        return {"sent": True, "id": result["id"], "project": project}

    def _tool_check_inbox(self, project: str | None = None, limit: int = 10) -> dict:
        result = self.svc.message_manager.inbox(project=project, limit=min(limit, 20))
        return {
            "count": result["total"],
            "messages": [
                {
                    "id": m["id"],
                    "sender": m["sender"],
                    "content": m["content"],
                    "priority": m["priority"],
                    "is_read": m["is_read"],
                    "project": m["project"],
                    "created_at": m["created_at"],
                }
                for m in result["items"]
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
                    "short_id": i["short_id"],
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
            "short_id": result["short_id"],
            "project": project,
            "title": title,
        }
