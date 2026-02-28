"""Agent definition and dashboard REST endpoints (ca-150, ca-159)."""

from __future__ import annotations

from fastapi import APIRouter, Path, Query

from cairn.core.agent_dashboard import AgentDashboard
from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    registry = svc.agent_registry
    if not registry:
        return

    @router.get("/agents")
    def api_list_agents(role: str | None = Query(None)):
        if role:
            return [d.to_dict() for d in registry.list_by_role(role)]
        return registry.to_dict()

    @router.get("/agents/{name}")
    def api_get_agent(name: str = Path(...)):
        defn = registry.get(name)
        if not defn:
            return {"error": f"Agent '{name}' not found"}
        return defn.to_dict()

    # --- Multi-agent dashboard (ca-159) ---

    dashboard = AgentDashboard(db=svc.db)

    @router.get("/agents/dashboard/overview")
    def api_agent_dashboard(project: str | None = Query(None)):
        """Multi-agent dashboard — active agents, locks, and health."""
        return dashboard.overview(project)

    @router.get("/agents/dashboard/active")
    def api_active_agents(project: str | None = Query(None)):
        """List active agents with their work items and heartbeat status."""
        return dashboard.active_agents(project)

    @router.get("/agents/dashboard/{agent_name}")
    def api_agent_detail(agent_name: str = Path(...)):
        """Detailed view of a single agent's state and history."""
        return dashboard.agent_detail(agent_name)
