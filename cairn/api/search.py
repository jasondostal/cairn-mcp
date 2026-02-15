"""Search and timeline endpoints."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.api.utils import parse_multi
from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    search_engine = svc.search_engine
    memory_store = svc.memory_store

    @router.get("/timeline")
    def api_timeline(
        project: str | None = Query(None),
        type: str | None = Query(None),
        days: int = Query(7, ge=1, le=365),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        projects = parse_multi(project)
        types = parse_multi(type)

        where = ["m.is_active = true", "m.created_at >= %s"]
        params: list = [cutoff]

        if projects:
            where.append("p.name = ANY(%s)")
            params.append(projects)
        if types:
            where.append("m.memory_type = ANY(%s)")
            params.append(types)

        where_clause = " AND ".join(where)

        count_row = db.execute_one(
            f"""
            SELECT COUNT(*) as total FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total = count_row["total"]

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = db.execute(
            f"""
            SELECT m.id, m.summary, m.content, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.is_active,
                   m.session_name, m.author, m.created_at, m.updated_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            ORDER BY m.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "summary": r["summary"],
                "content": r["content"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "related_files": r["related_files"],
                "is_active": r["is_active"],
                "session_name": r["session_name"],
                "author": r.get("author"),
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @router.get("/search")
    def api_search(
        q: str = Query(..., description="Search query"),
        project: str | None = Query(None),
        type: str | None = Query(None),
        mode: str = Query("semantic"),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        results = search_engine.search(
            query=q,
            project=parse_multi(project),
            memory_type=parse_multi(type),
            search_mode=mode,
            limit=limit + offset,
            include_full=True,
        )
        items = results[offset:offset + limit]
        return {"total": len(results), "limit": limit, "offset": offset, "items": items}

    @router.get("/memories/{memory_id}")
    def api_memory(memory_id: int = Path(...)):
        results = memory_store.recall([memory_id])
        if not results:
            raise HTTPException(status_code=404, detail="Memory not found")
        return results[0]
