"""Event subscription and notification REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services


class CreateSubscriptionBody(BaseModel):
    name: str
    patterns: list[str]
    channel: str = "in_app"
    channel_config: dict | None = None
    project: str | None = None


class UpdateSubscriptionBody(BaseModel):
    name: str | None = None
    patterns: list[str] | None = None
    channel: str | None = None
    channel_config: dict | None = None
    is_active: bool | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    sm = svc.subscription_manager
    if not sm:
        return

    # --- Subscriptions ---

    @router.get("/subscriptions")
    def api_list_subscriptions(
        channel: str | None = Query(None),
        project: str | None = Query(None),
    ):
        return sm.list(channel=channel, project=project)

    @router.post("/subscriptions", status_code=201)
    def api_create_subscription(body: CreateSubscriptionBody = Body(...)):
        return sm.create(
            name=body.name,
            patterns=body.patterns,
            channel=body.channel,
            channel_config=body.channel_config,
            project=body.project,
        )

    @router.get("/subscriptions/{sub_id}")
    def api_get_subscription(sub_id: int = Path(...)):
        result = sm.get(sub_id)
        if not result:
            return {"error": "Subscription not found"}
        return result

    @router.patch("/subscriptions/{sub_id}")
    def api_update_subscription(
        sub_id: int = Path(...),
        body: UpdateSubscriptionBody = Body(...),
    ):
        return sm.update(sub_id, **body.model_dump(exclude_none=True))

    @router.delete("/subscriptions/{sub_id}")
    def api_delete_subscription(sub_id: int = Path(...)):
        return sm.delete(sub_id)

    # --- Notifications ---

    @router.get("/notifications")
    def api_list_notifications(
        unread_only: bool = Query(False),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return sm.list_notifications(unread_only=unread_only, limit=limit, offset=offset)

    @router.get("/notifications/unread-count")
    def api_unread_count():
        return {"unread": sm.unread_count()}

    @router.post("/notifications/{notif_id}/read")
    def api_mark_read(notif_id: int = Path(...)):
        return sm.mark_read(notif_id)

    @router.post("/notifications/read-all")
    def api_mark_all_read():
        return sm.mark_all_read()

    # --- Push ---

    @router.get("/push/status")
    def api_push_status():
        pn = sm.push_notifier
        if not pn or not pn.enabled:
            return {"enabled": False}
        return {
            "enabled": True,
            "url": svc.config.push.url,
            "topic": svc.config.push.default_topic,
        }

    @router.post("/push/test")
    def api_push_test(
        title: str = Body("Cairn test notification", embed=True),
        body: str = Body("If you see this, push notifications are working!", embed=True),
    ):
        pn = sm.push_notifier
        if not pn or not pn.enabled:
            return {"sent": False, "error": "Push notifications not configured"}
        sent = pn.send(
            title=title,
            body=body,
            severity="info",
            tags=["test_tube"],
        )
        return {"sent": sent}
