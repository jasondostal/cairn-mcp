"""Workspace endpoints — agent backend integration."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    workspace_manager = svc.workspace_manager

    @router.get("/workspace/health")
    def api_workspace_health():
        return workspace_manager.health()

    @router.get("/workspace/backends")
    def api_workspace_backends():
        """List configured workspace backends with capabilities and health."""
        return workspace_manager.list_backends()

    @router.get("/workspace/sessions")
    def api_workspace_sessions(
        project: str | None = Query(None),
    ):
        return workspace_manager.list_sessions(project=project)

    @router.post("/workspace/sessions", status_code=201)
    def api_workspace_create_session(body: dict):
        project = body.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        return workspace_manager.create_session(
            project=project,
            task=body.get("task"),
            message_id=body.get("message_id"),
            fork_from=body.get("fork_from"),
            title=body.get("title"),
            agent=body.get("agent"),
            inject_context=body.get("inject_context", True),
            context_mode=body.get("context_mode", "focused"),
            backend=body.get("backend"),
            risk_tier=body.get("risk_tier"),
            work_item_id=body.get("work_item_id"),
            model=body.get("model"),
        )

    @router.get("/workspace/sessions/{session_id}")
    def api_workspace_get_session(session_id: str = Path(...)):
        result = workspace_manager.get_session(session_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @router.delete("/workspace/sessions/{session_id}")
    def api_workspace_delete_session(session_id: str = Path(...)):
        return workspace_manager.delete_session(session_id)

    @router.post("/workspace/sessions/{session_id}/message")
    def api_workspace_send_message(session_id: str = Path(...), body: dict = {}):
        text = body.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        return workspace_manager.send_message(
            session_id=session_id,
            text=text,
            agent=body.get("agent"),
            wait=body.get("wait", True),
        )

    @router.post("/workspace/sessions/{session_id}/abort")
    def api_workspace_abort_session(session_id: str = Path(...)):
        return workspace_manager.abort_session(session_id)

    @router.get("/workspace/sessions/{session_id}/diff")
    def api_workspace_get_diff(session_id: str = Path(...)):
        return workspace_manager.get_diff(session_id)

    @router.get("/workspace/sessions/{session_id}/messages")
    def api_workspace_messages(session_id: str = Path(...)):
        return workspace_manager.get_messages(session_id)

    @router.get("/workspace/agents")
    def api_workspace_agents():
        return workspace_manager.list_agents()

    @router.get("/workspace/context/{project}")
    def api_workspace_context(
        project: str = Path(...),
        task: str | None = Query(None),
    ):
        return {"context": workspace_manager.build_context(project, task=task)}
