"""Real-time metrics SSE stream — system EKG endpoint.

GET /api/metrics/stream — continuous 1-second pulse of operational metrics.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Query
from starlette.responses import StreamingResponse

from cairn.core import stats
from cairn.core.constants import EVENT_STREAM_HEARTBEAT_INTERVAL
from cairn.core.metrics_collector import MetricsCollector
from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **kw):
    metrics_collector: MetricsCollector | None = kw.get("metrics_collector")

    @router.get("/metrics/stream")
    async def api_metrics_stream(
        include_history: bool = Query(False, description="Send last 60 seconds on connect"),
    ):
        """SSE endpoint streaming real-time operational metrics (1 pulse/second)."""
        if metrics_collector is None:
            return {"error": "Metrics collector not initialized"}

        async def event_generator():
            if stats.event_bus_stats:
                stats.event_bus_stats.record_sse_connect()

            q = await metrics_collector.subscribe()
            try:
                # Send history if requested
                if include_history:
                    for bucket in metrics_collector.history():
                        yield f"event: metric\ndata: {json.dumps(bucket.to_dict())}\n\n"

                last_heartbeat = time.monotonic()

                while True:
                    try:
                        bucket = await asyncio.wait_for(
                            q.get(), timeout=EVENT_STREAM_HEARTBEAT_INTERVAL,
                        )
                        yield f"event: metric\ndata: {json.dumps(bucket.to_dict())}\n\n"
                        if stats.event_bus_stats:
                            stats.event_bus_stats.record_sse_event()
                        last_heartbeat = time.monotonic()
                    except TimeoutError:
                        # No bucket received — send heartbeat
                        now = time.monotonic()
                        if now - last_heartbeat >= EVENT_STREAM_HEARTBEAT_INTERVAL:
                            yield f"event: heartbeat\ndata: {json.dumps({})}\n\n"
                            last_heartbeat = now

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("Metrics SSE stream error: %s", e, exc_info=True)
                if stats.event_bus_stats:
                    stats.event_bus_stats.record_error(f"Metrics SSE: {e}")
                yield f"event: error\ndata: {json.dumps({'message': 'Internal server error'})}\n\n"
            finally:
                metrics_collector.unsubscribe(q)
                if stats.event_bus_stats:
                    stats.event_bus_stats.record_sse_disconnect()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/metrics/snapshot")
    def api_metrics_snapshot():
        """Return the current metrics bucket (point-in-time snapshot)."""
        if metrics_collector is None:
            return {"error": "Metrics collector not initialized"}
        return metrics_collector.snapshot().to_dict()
