"""Dispatch endpoint — send work to a background agent."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from cairn.core.services import Services

logger = logging.getLogger(__name__)


class DispatchBody(BaseModel):
    work_item_id: int | str | None = None
    project: str | None = None
    title: str | None = None
    description: str | None = None
    backend: str | None = None
    risk_tier: int | None = None
    model: str | None = None
    agent: str | None = None
    assignee: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    workspace_manager = svc.workspace_manager

    @router.post("/dispatch")
    def api_dispatch(body: DispatchBody = Body(...)):
        from cairn.api.utils import require_admin
        admin_err = require_admin()
        if admin_err:
            return admin_err
        try:
            return workspace_manager.dispatch(
                work_item_id=body.work_item_id,
                project=body.project,
                title=body.title,
                description=body.description,
                backend=body.backend,
                risk_tier=body.risk_tier,
                model=body.model,
                agent=body.agent,
                assignee=body.assignee,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("dispatch failed")
            raise HTTPException(status_code=500, detail=f"Dispatch failed: {e}") from e
