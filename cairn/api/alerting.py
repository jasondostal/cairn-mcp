"""REST endpoints for health alerting (Watchtower Phase 4).

Rule CRUD, alert history, active alerts, and built-in templates.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from cairn.core.alerting import ALERT_TEMPLATES
from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    alert_mgr = svc.alert_manager
    if not alert_mgr:
        return  # Alerting disabled

    # ------------------------------------------------------------------
    # Rule CRUD
    # ------------------------------------------------------------------

    @router.post("/alerts/rules", tags=["alerting"])
    async def create_rule(body: dict[str, Any]):
        name = body.get("name", "").strip()
        if not name:
            return {"error": "name is required"}, 400

        condition_type = body.get("condition_type", "").strip()
        if not condition_type:
            return {"error": "condition_type is required"}, 400

        condition = body.get("condition")
        if not condition or not isinstance(condition, dict):
            return {"error": "condition (dict) is required"}, 400

        rule = alert_mgr.create(
            name=name,
            condition_type=condition_type,
            condition=condition,
            notification=body.get("notification"),
            severity=body.get("severity", "warning"),
            cooldown_minutes=body.get("cooldown_minutes", 60),
        )
        return rule

    @router.get("/alerts/rules", tags=["alerting"])
    async def list_rules(
        is_active: bool | None = Query(None),
        severity: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return alert_mgr.list(
            is_active=is_active,
            severity=severity,
            limit=limit,
            offset=offset,
        )

    @router.get("/alerts/rules/{rule_id}", tags=["alerting"])
    async def get_rule(rule_id: int):
        rule = alert_mgr.get(rule_id)
        if not rule:
            return {"error": "Alert rule not found"}, 404
        return rule

    @router.patch("/alerts/rules/{rule_id}", tags=["alerting"])
    async def update_rule(rule_id: int, body: dict[str, Any]):
        rule = alert_mgr.update(rule_id, **body)
        if not rule:
            return {"error": "Alert rule not found"}, 404
        return rule

    @router.delete("/alerts/rules/{rule_id}", tags=["alerting"])
    async def delete_rule(rule_id: int):
        deleted = alert_mgr.delete(rule_id)
        if not deleted:
            return {"error": "Alert rule not found"}, 404
        return {"deleted": True}

    # ------------------------------------------------------------------
    # Alert history + active
    # ------------------------------------------------------------------

    @router.get("/alerts/history", tags=["alerting"])
    async def query_history(
        rule_id: int | None = Query(None),
        severity: str | None = Query(None),
        days: int | None = Query(None, ge=1, le=365),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return alert_mgr.query_history(
            rule_id=rule_id,
            severity=severity,
            days=days,
            limit=limit,
            offset=offset,
        )

    @router.get("/alerts/active", tags=["alerting"])
    async def active_alerts(
        hours: int = Query(24, ge=1, le=168),
    ):
        return alert_mgr.active_alerts(hours=hours)

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    @router.get("/alerts/templates", tags=["alerting"])
    async def list_templates():
        return {
            "templates": {
                key: {**tmpl}
                for key, tmpl in ALERT_TEMPLATES.items()
            }
        }
