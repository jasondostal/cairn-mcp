"""Cairn MCP tool modules, grouped by domain.

Post-cut (v0.80.0): memory core tools only. Agent tools removed.

Tools are registered in two tiers:
- Core: always registered (memory, insights, work items, project)
- Extended: gated behind CAIRN_EXTENDED_TOOLS=true (work_items tools)
"""

import logging

from cairn.core.services import Services
from cairn.tools.insights import register as register_insights
from cairn.tools.memory import register as register_memory
from cairn.tools.project import register as register_project
from cairn.tools.work_items import register as register_work_items

logger = logging.getLogger("cairn")


def register_all(mcp, svc: Services):
    """Register all tool modules.

    Core tools are always registered. Extended tools register only when
    CAIRN_EXTENDED_TOOLS is enabled.

    Args:
        mcp: FastMCP instance.
        svc: Initialized Services dataclass.
    """
    # Core tools — always available
    register_memory(mcp, svc)
    register_insights(mcp, svc)
    register_project(mcp, svc)

    # Work items — gated (experimental)
    if svc.config.extended_tools:
        register_work_items(mcp, svc)
        logger.info("Extended tools registered (work_items)")
    else:
        logger.info("Extended tools disabled (set CAIRN_EXTENDED_TOOLS=true to enable)")
