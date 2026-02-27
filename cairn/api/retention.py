"""Retention API endpoints — policy CRUD, preview, and status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cairn.core.services import Services


class RetentionCreate(BaseModel):
    resource_type: str
    ttl_days: int
    project_id: str | None = None
    legal_hold: bool = False


class RetentionUpdate(BaseModel):
    resource_type: str | None = None
    ttl_days: int | None = None
    project_id: str | None = None
    legal_hold: bool | None = None
    is_active: bool | None = None


class PreviewRequest(BaseModel):
    policy_id: int | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    mgr = svc.retention_manager
    if not mgr:
        return

    @router.post("/retention/policies")
    def create_policy(body: RetentionCreate):
        try:
            return mgr.create(
                resource_type=body.resource_type,
                ttl_days=body.ttl_days,
                project_id=body.project_id,
                legal_hold=body.legal_hold,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @router.get("/retention/policies")
    def list_policies(
        resource_type: str | None = None,
        project_id: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return mgr.list(
            resource_type=resource_type,
            project_id=project_id,
            is_active=is_active,
            limit=min(limit, 100),
            offset=offset,
        )

    @router.get("/retention/policies/{policy_id}")
    def get_policy(policy_id: int):
        result = mgr.get(policy_id)
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found")
        return result

    @router.patch("/retention/policies/{policy_id}")
    def update_policy(policy_id: int, body: RetentionUpdate):
        result = mgr.update(policy_id, **body.model_dump(exclude_none=True))
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found")
        return result

    @router.delete("/retention/policies/{policy_id}")
    def delete_policy(policy_id: int):
        if not mgr.delete(policy_id):
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"deleted": True}

    @router.post("/retention/preview")
    def preview(body: PreviewRequest = PreviewRequest()):
        return {"results": mgr.preview(body.policy_id)}

    @router.get("/retention/status")
    def retention_status():
        return mgr.status()
