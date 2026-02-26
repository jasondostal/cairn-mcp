"""Webhook endpoints — CRUD, test delivery, and delivery history."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services
from cairn.core.webhooks import sign_payload


class CreateWebhookBody(BaseModel):
    name: str
    url: str
    event_types: list[str]
    project: str | None = None
    metadata: dict | None = None


class UpdateWebhookBody(BaseModel):
    name: str | None = None
    url: str | None = None
    event_types: list[str] | None = None
    is_active: bool | None = None
    metadata: dict | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    webhook_mgr = svc.webhook_manager

    if not webhook_mgr:
        return

    db = svc.db

    def _resolve_project_id(project_name: str | None) -> int | None:
        if not project_name:
            return None
        row = db.execute_one(
            "SELECT id FROM projects WHERE name = %s", (project_name,)
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        return row["id"]

    @router.post("/webhooks")
    def api_create_webhook(body: CreateWebhookBody):
        project_id = _resolve_project_id(body.project)
        return webhook_mgr.create(
            name=body.name,
            url=body.url,
            event_types=body.event_types,
            project_id=project_id,
            metadata=body.metadata,
        )

    @router.get("/webhooks")
    def api_list_webhooks(
        project: str | None = Query(None),
        active_only: bool = Query(True),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        project_id = _resolve_project_id(project) if project else None
        return webhook_mgr.list(
            project_id=project_id,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

    @router.get("/webhooks/{webhook_id}")
    def api_get_webhook(webhook_id: int = Path(...)):
        hook = webhook_mgr.get(webhook_id)
        if not hook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return hook

    @router.patch("/webhooks/{webhook_id}")
    def api_update_webhook(body: UpdateWebhookBody, webhook_id: int = Path(...)):
        updates = body.model_dump(exclude_none=True)
        result = webhook_mgr.update(webhook_id, **updates)
        if not result:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return result

    @router.delete("/webhooks/{webhook_id}")
    def api_delete_webhook(webhook_id: int = Path(...)):
        if not webhook_mgr.delete(webhook_id):
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted"}

    @router.post("/webhooks/{webhook_id}/rotate-secret")
    def api_rotate_secret(webhook_id: int = Path(...)):
        result = webhook_mgr.rotate_secret(webhook_id)
        if not result:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return result

    @router.post("/webhooks/{webhook_id}/test")
    def api_test_webhook(webhook_id: int = Path(...)):
        """Send a synchronous test delivery to verify connectivity."""
        hook = webhook_mgr.get(webhook_id)
        if not hook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        test_payload = {
            "event_type": "webhook.test",
            "webhook_id": hook["id"],
            "webhook_name": hook["name"],
            "message": "This is a test delivery from Cairn.",
        }

        payload_bytes = json.dumps(test_payload, separators=(",", ":")).encode("utf-8")
        signature = sign_payload(payload_bytes, hook["secret"])

        req = urllib.request.Request(
            hook["url"],
            data=payload_bytes,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Cairn-Webhook/1.0",
                "X-Cairn-Signature": f"sha256={signature}",
                "X-Cairn-Event": "webhook.test",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {
                    "status": "success",
                    "http_status": resp.status,
                    "body": resp.read().decode("utf-8", errors="replace")[:2000],
                }
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass
            return {
                "status": "error",
                "http_status": exc.code,
                "body": body,
            }
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            return {
                "status": "error",
                "error": str(e),
            }

    @router.get("/webhooks/{webhook_id}/deliveries")
    def api_webhook_deliveries(
        webhook_id: int = Path(...),
        status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        if not webhook_mgr.get(webhook_id):
            raise HTTPException(status_code=404, detail="Webhook not found")
        return webhook_mgr.list_deliveries(
            webhook_id=webhook_id,
            status=status,
            limit=limit,
            offset=offset,
        )
