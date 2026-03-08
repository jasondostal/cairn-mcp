"""Agent tools: affinity-based agent suggestion."""

import logging

from cairn.core.services import Services
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.tools.auth import check_project_access
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register agent-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def suggest_agent(
        work_item_id: int | str | None = None,
        project: str | None = None,
        title: str | None = None,
        description: str | None = None,
        item_type: str | None = None,
        risk_tier: int | None = None,
    ) -> dict:
        """Affinity-based agent suggestion for a work item.

        Provide either work_item_id (to look up existing item) or
        project + title + description (to match against a proposed item).

        Returns ranked agent suggestions with affinity scores and any
        disqualified agents with reasons.

        Args:
            work_item_id: Existing work item ID to suggest agents for.
            project: Project name (for ad-hoc matching without existing item).
            title: Work item title (for ad-hoc matching).
            description: Work item description (for ad-hoc matching).
            item_type: Item type hint (default: task).
            risk_tier: Risk tier hint for matching.
        """
        try:
            set_trace_tool("suggest_agent")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_suggest_agent():
                from cairn.core.affinity import rank_agents
                from cairn.core.agents import AgentRegistry

                registry = AgentRegistry()
                work_item_manager = svc.work_item_manager

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

            return await in_thread(svc.db, _do_suggest_agent)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("suggest_agent failed")
            return {"error": f"Internal error: {e}"}
