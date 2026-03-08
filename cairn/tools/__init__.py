"""Cairn MCP tool modules, grouped by domain."""

from cairn.core.services import Services
from cairn.tools.insights import register as register_insights
from cairn.tools.memory import register as register_memory
from cairn.tools.project import register as register_project
from cairn.tools.session import register as register_session
from cairn.tools.work_items import register as register_work_items


def register_all(mcp, svc: Services):
    """Register all tool modules.

    Args:
        mcp: FastMCP instance.
        svc: Initialized Services dataclass (typed, with autocomplete).
    """
    register_memory(mcp, svc)
    register_work_items(mcp, svc)
    register_insights(mcp, svc)
    register_session(mcp, svc)
    register_project(mcp, svc)
