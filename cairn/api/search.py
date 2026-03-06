"""Search, timeline, and memory CRUD endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel

from cairn.api.utils import parse_multi
from cairn.core.services import Services


class StoreMemoryBody(BaseModel):
    content: str
    project: str
    memory_type: str = "note"
    importance: float = 0.5
    tags: list[str] | None = None
    session_name: str | None = None
    related_files: list[str] | None = None
    related_ids: list[int] | None = None
    file_hashes: dict[str, str] | None = None
    author: str | None = None


class UpdateMemoryBody(BaseModel):
    content: str | None = None
    memory_type: str | None = None
    importance: float | None = None
    tags: list[str] | None = None
    project: str | None = None
    author: str | None = None


class InactivateBody(BaseModel):
    reason: str


class RecallBody(BaseModel):
    ids: list[int]


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    search_engine = svc.search_engine
    memory_store = svc.memory_store

    @router.get("/timeline")
    def api_timeline(
        project: str | None = Query(None),
        type: str | None = Query(None),
        session_name: str | None = Query(None),
        days: int = Query(7, ge=1, le=365),
        sort: str = Query("recent", pattern="^(recent|important|relevance)$"),
        group_by: str = Query("none", pattern="^(none|type)$"),
        include_clusters: bool = Query(False),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        cutoff = datetime.now(UTC) - timedelta(days=days)
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
        if session_name:
            where.append("m.session_name = %s")
            params.append(session_name)

        where_clause = " AND ".join(where)

        # Sort clause
        sort_clauses = {
            "recent": "m.created_at DESC",
            "important": "m.importance DESC, m.created_at DESC",
            "relevance": "m.importance * (1.0 / (1 + EXTRACT(EPOCH FROM NOW() - m.created_at) / 86400.0)) DESC",
        }
        order_by = sort_clauses.get(sort, sort_clauses["recent"])

        count_row = db.execute_one(
            f"""
            SELECT COUNT(*) as total FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        assert count_row is not None
        total = count_row["total"]

        # Optional cluster join
        cluster_select = ""
        cluster_join = ""
        if include_clusters:
            cluster_select = ", cl.id as cluster_id, cl.label as cluster_label, cl.member_count as cluster_size"
            cluster_join = """
                LEFT JOIN LATERAL (
                    SELECT c.id, c.label, c.member_count
                    FROM cluster_members cm
                    JOIN clusters c ON c.id = cm.cluster_id
                    WHERE cm.memory_id = m.id
                    ORDER BY c.confidence DESC
                    LIMIT 1
                ) cl ON true
            """

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = db.execute(
            f"""
            SELECT m.id, m.summary, m.content, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.is_active,
                   m.session_name, m.author, m.created_at, m.updated_at,
                   p.name as project
                   {cluster_select}
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            {cluster_join}
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        def row_to_item(r):
            item = {
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
            if include_clusters and r.get("cluster_id"):
                item["cluster"] = {
                    "id": r["cluster_id"],
                    "label": r["cluster_label"],
                    "size": r["cluster_size"],
                }
            return item

        items = [row_to_item(r) for r in rows]

        if group_by == "type":
            groups: dict[str, list] = {}
            for item in items:
                mt = item["memory_type"]
                groups.setdefault(mt, []).append(item)
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "group_by": "type",
                "groups": [
                    {"type": t, "count": len(g), "items": g}
                    for t, g in sorted(groups.items(), key=lambda x: -len(x[1]))
                ],
            }

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

    @router.get("/memories/{memory_id}/work-items")
    def api_memory_work_items(memory_id: int = Path(...)):
        from cairn.core.utils import make_display_id

        rows = db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.status, wi.item_type,
                   p.name as project, p.work_item_prefix
            FROM work_item_memory_links wml
            JOIN work_items wi ON wi.id = wml.work_item_id
            LEFT JOIN projects p ON wi.project_id = p.id
            WHERE wml.memory_id = %s
            ORDER BY wi.created_at DESC
            """,
            (memory_id,),
        )
        return {
            "memory_id": memory_id,
            "work_items": [
                {
                    "id": r["id"],
                    "display_id": make_display_id(r["work_item_prefix"], r["seq_num"]),
                    "title": r["title"],
                    "status": r["status"],
                    "item_type": r["item_type"],
                    "project": r["project"],
                }
                for r in rows
            ],
        }

    # --- Memory CRUD ---

    @router.post("/memories", status_code=201)
    def api_store_memory(body: StoreMemoryBody = Body(...)):
        return memory_store.store(
            content=body.content,
            project=body.project,
            memory_type=body.memory_type,
            importance=body.importance,
            tags=body.tags,
            session_name=body.session_name,
            related_files=body.related_files,
            related_ids=body.related_ids,
            file_hashes=body.file_hashes,
            author=body.author,
        )

    @router.patch("/memories/{memory_id}")
    def api_update_memory(memory_id: int = Path(...), body: UpdateMemoryBody = Body(...)):
        fields = body.model_dump(exclude_none=True)
        if not fields:
            return {"id": memory_id, "action": "no_changes"}
        return memory_store.modify(
            memory_id, "update",
            content=body.content,
            memory_type=body.memory_type,
            importance=body.importance,
            tags=body.tags,
            project=body.project,
            author=body.author,
        )

    @router.post("/memories/{memory_id}/inactivate")
    def api_inactivate_memory(memory_id: int = Path(...), body: InactivateBody = Body(...)):
        return memory_store.modify(memory_id, "inactivate", reason=body.reason)

    @router.post("/memories/{memory_id}/reactivate")
    def api_reactivate_memory(memory_id: int = Path(...)):
        return memory_store.modify(memory_id, "reactivate")

    @router.post("/memories/recall")
    def api_recall_memories(body: RecallBody = Body(...)):
        if len(body.ids) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 IDs per recall request")
        return memory_store.recall(body.ids)
