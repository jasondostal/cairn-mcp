"""Analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    analytics_engine = svc.analytics_engine

    if not analytics_engine:
        return

    @router.get("/analytics/overview")
    def api_analytics_overview(
        days: int = Query(7, ge=1, le=365),
    ):
        return analytics_engine.overview(days=days)

    @router.get("/analytics/timeseries")
    def api_analytics_timeseries(
        days: int = Query(7, ge=1, le=365),
        granularity: str = Query("hour"),
        project: str | None = Query(None),
        operation: str | None = Query(None),
    ):
        if granularity not in ("hour", "day"):
            granularity = "hour"
        return analytics_engine.timeseries(
            days=days, granularity=granularity,
            project=project, operation=operation,
        )

    @router.get("/analytics/operations")
    def api_analytics_operations(
        days: int = Query(7, ge=1, le=365),
        project: str | None = Query(None),
        operation: str | None = Query(None),
        success: bool | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return analytics_engine.operations(
            days=days, project=project, operation=operation,
            success=success, limit=limit, offset=offset,
        )

    @router.get("/analytics/projects")
    def api_analytics_projects(
        days: int = Query(7, ge=1, le=365),
    ):
        return analytics_engine.projects_breakdown(days=days)

    @router.get("/analytics/models")
    def api_analytics_models(
        days: int = Query(7, ge=1, le=365),
    ):
        return analytics_engine.models_performance(days=days)

    @router.get("/analytics/memory-growth")
    def api_analytics_memory_growth(
        days: int = Query(90, ge=1, le=365),
        granularity: str = Query("day"),
    ):
        if granularity not in ("hour", "day"):
            granularity = "day"
        return analytics_engine.memory_type_growth(days=days, granularity=granularity)

    @router.get("/analytics/sparklines")
    def api_analytics_sparklines(
        days: int = Query(30, ge=1, le=365),
    ):
        return analytics_engine.entity_counts_sparkline(days=days)

    @router.get("/analytics/heatmap")
    def api_analytics_heatmap(
        days: int = Query(365, ge=1, le=365),
    ):
        return analytics_engine.activity_heatmap(days=days)

    @router.get("/analytics/token-budget")
    def api_analytics_token_budget(
        days: int = Query(7, ge=1, le=365),
    ):
        return analytics_engine.daily_token_budget(days=days)
