"""Event bus endpoints — publish, query, and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from cairn.core.constants import EVENT_STREAM_HEARTBEAT_INTERVAL
from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    event_bus = svc.event_bus
    db = svc.db

    @router.post("/events", status_code=201)
    def api_post_event(body: dict):
        """Publish a single event."""
        session_name = body.get("session_name")
        event_type = body.get("event_type")

        if not session_name:
            raise HTTPException(status_code=400, detail="session_name is required")
        if not event_type:
            raise HTTPException(status_code=400, detail="event_type is required")

        event_id = event_bus.publish(
            session_name=session_name,
            event_type=event_type,
            project=body.get("project"),
            agent_id=body.get("agent_id"),
            work_item_id=body.get("work_item_id"),
            tool_name=body.get("tool_name"),
            payload=body.get("payload"),
        )

        return {"id": event_id, "status": "published"}

    @router.get("/events")
    def api_get_events(
        session_name: str | None = Query(None),
        work_item_id: int | None = Query(None),
        event_type: str | None = Query(None),
        project: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        order: str = Query("desc", pattern="^(asc|desc)$"),
    ):
        """Query events with filters."""
        return event_bus.query(
            session_name=session_name,
            work_item_id=work_item_id,
            event_type=event_type,
            project=project,
            limit=limit,
            offset=offset,
            order=order,
        )

    @router.get("/events/stream")
    async def api_events_stream(
        session_name: str | None = Query(None),
        event_type: str | None = Query(None),
    ):
        """SSE endpoint using Postgres LISTEN on cairn_events channel."""

        async def event_generator():
            import psycopg

            # Get a raw connection for LISTEN (can't use pooled connections)
            dsn = db._dsn
            try:
                conn = await psycopg.AsyncConnection.connect(
                    dsn, autocommit=True,
                )
            except Exception as e:
                logger.error("SSE: failed to connect for LISTEN: %s", e)
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
                return

            try:
                await conn.execute("LISTEN cairn_events")

                last_heartbeat = time.monotonic()

                while True:
                    # Wait for notification with timeout for heartbeat
                    try:
                        async for notify in conn.notifies(
                            timeout=EVENT_STREAM_HEARTBEAT_INTERVAL,
                        ):
                            try:
                                data = json.loads(notify.payload)
                            except (json.JSONDecodeError, TypeError):
                                continue

                            # Apply filters
                            if session_name and data.get("session_name") != session_name:
                                continue
                            if event_type and data.get("event_type") != event_type:
                                continue

                            yield f"event: event\ndata: {json.dumps(data, default=str)}\n\n"
                            last_heartbeat = time.monotonic()
                            break  # Process one at a time to check heartbeat
                    except asyncio.TimeoutError:
                        pass

                    # Send heartbeat if needed
                    now = time.monotonic()
                    if now - last_heartbeat >= EVENT_STREAM_HEARTBEAT_INTERVAL:
                        yield f"event: heartbeat\ndata: {json.dumps({'ts': int(now)})}\n\n"
                        last_heartbeat = now

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("SSE stream error: %s", e, exc_info=True)
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            finally:
                await conn.close()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
