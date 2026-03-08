"""Session tools: orient, status, rules, working_memory."""

import logging

from cairn.core.budget import apply_list_budget
from cairn.core.constants import BUDGET_RULES_PER_ITEM, MAX_LIMIT
from cairn.core.services import Services
from cairn.core.status import get_status
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.tools.auth import check_project_access
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register session-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

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
            set_trace_tool("rules")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_rules():
                result = svc.memory_store.get_rules(project)
                items = result["items"]
                budget = svc.config.budget.rules
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

            return await in_thread(svc.db, _do_rules)
        except Exception as e:
            logger.exception("rules failed")
            return [{"error": f"Internal error: {e}"}]

    @mcp.tool()
    async def status() -> dict:
        """System health and statistics.

        WHEN TO USE: Health checks, system overview, "how many memories", "is cairn working",
        verifying deployment status. Quick diagnostic tool — no parameters required.
        """
        try:
            set_trace_tool("status")
            return await in_thread(svc.db, get_status, svc.db, svc.config)
        except Exception as e:
            logger.exception("status failed")
            return {"error": f"Internal error: {e}"}

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
            set_trace_tool("orient")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_orient():
                return run_orient(
                    project=project,
                    config=svc.config,
                    db=svc.db,
                    memory_store=svc.memory_store,
                    search_engine=svc.search_engine,
                    work_item_manager=svc.work_item_manager,
                    task_manager=svc.task_manager,
                    graph_provider=svc.graph_provider,
                    belief_store=svc.belief_store,
                )

            return await in_thread(svc.db, _do_orient)
        except Exception as e:
            logger.exception("orient failed")
            return {"error": f"Internal error: {e}"}

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
            set_trace_tool("working_memory")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_working_memory():
                memory_store = svc.memory_store

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

            return await in_thread(svc.db, _do_working_memory)
        except Exception as e:
            logger.exception("working_memory failed")
            return {"error": f"Internal error: {e}"}


def _fetch_trail_data(svc: Services, project=None, since=None, limit=20):
    """Fetch recent activity trail data. Used by trail() tool."""
    from cairn.core.orient import fetch_trail_data
    return fetch_trail_data(
        db=svc.db, graph_provider=svc.graph_provider,
        project=project, since=since, limit=limit,
    )
