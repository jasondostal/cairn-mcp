"""Session tools: orient, status, rules."""

import logging

from cairn.core.budget import apply_list_budget
from cairn.core.constants import BUDGET_RULES_PER_ITEM
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
                    graph_provider=svc.graph_provider,
                    belief_store=svc.belief_store,
                )

            return await in_thread(svc.db, _do_orient)
        except Exception as e:
            logger.exception("orient failed")
            return {"error": f"Internal error: {e}"}



def _fetch_trail_data(svc: Services, project=None, since=None, limit=20):
    """Fetch recent activity trail data. Used by trail() tool."""
    from cairn.core.orient import fetch_trail_data
    return fetch_trail_data(
        db=svc.db, graph_provider=svc.graph_provider,
        project=project, since=since, limit=limit,
    )
