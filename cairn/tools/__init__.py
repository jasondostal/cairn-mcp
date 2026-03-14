"""Cairn MCP tool modules, grouped by domain.

Tools are registered in two tiers:
- Core: always registered (memory, search, work items, projects, session)
- Extended: gated behind CAIRN_EXTENDED_TOOLS=true (deliverables, locks,
  suggest_agent, decay_scan, drift_check). These are fully implemented but
  add schema weight for MCP clients that don't need them.
"""

import logging

from cairn.core.services import Services
from cairn.tools.insights import register as register_insights
from cairn.tools.memory import register as register_memory
from cairn.tools.project import register as register_project
from cairn.tools.session import register as register_session
from cairn.tools.work_items import register as register_work_items

logger = logging.getLogger("cairn")


def register_all(mcp, svc: Services):
    """Register all tool modules.

    Core tools are always registered. Extended tools (deliverables, locks,
    suggest_agent) register only when CAIRN_EXTENDED_TOOLS is enabled.

    Args:
        mcp: FastMCP instance.
        svc: Initialized Services dataclass (typed, with autocomplete).
    """
    # Core tools — always available
    register_memory(mcp, svc)
    register_work_items(mcp, svc)
    register_insights(mcp, svc)
    register_session(mcp, svc)
    register_project(mcp, svc)

    # Extended tools — gated for clients that need them
    if svc.config.extended_tools:
        from cairn.tools.agents import register as register_agents
        from cairn.tools.deliverables import register as register_deliverables
        from cairn.tools.locks import register as register_locks

        register_deliverables(mcp, svc)
        register_locks(mcp, svc)
        register_agents(mcp, svc)
        logger.info("Extended tools registered (deliverables, locks, suggest_agent)")
    else:
        logger.info("Extended tools disabled (set CAIRN_EXTENDED_TOOLS=true to enable)")
