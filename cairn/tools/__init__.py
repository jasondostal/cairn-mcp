"""Cairn MCP tool modules, grouped by domain."""

from cairn.tools.insights import register as register_insights
from cairn.tools.memory import register as register_memory
from cairn.tools.project import register as register_project
from cairn.tools.session import register as register_session
from cairn.tools.work_items import register as register_work_items


def register_all(mcp, g):
    """Register all tool modules.

    Args:
        mcp: FastMCP instance.
        g: Dict of module-level globals from server.py (db, config, etc.).
    """
    register_memory(mcp, g)
    register_work_items(mcp, g)
    register_insights(mcp, g)
    register_session(mcp, g)
    register_project(mcp, g)
