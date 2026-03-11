"""Knowledge endpoints — projects, docs, clusters, rules, graph, analysis."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel

from cairn.api.utils import parse_multi
from cairn.core.services import Services
from cairn.core.utils import get_project

logger = logging.getLogger(__name__)


class ConsolidateBody(BaseModel):
    project: str
    dry_run: bool = True


class OrientBody(BaseModel):
    project: str | None = None


class LinkProjectBody(BaseModel):
    target: str
    link_type: str = "related"


class UpdatePrefixBody(BaseModel):
    prefix: str


class UpdateDocBody(BaseModel):
    content: str
    title: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    memory_store = svc.memory_store
    project_manager = svc.project_manager
    cluster_engine = svc.cluster_engine
    graph_provider = svc.graph_provider

    @router.get("/projects")
    def api_projects(
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return project_manager.list_all(limit=limit, offset=offset)

    @router.get("/projects/{name}")
    def api_project_detail(name: str = Path(...)):
        docs = project_manager.get_docs(name)
        links = project_manager.get_links(name)
        return {"name": name, "docs": docs, "links": links}

    @router.get("/docs")
    def api_docs(
        project: str | None = Query(None),
        doc_type: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return project_manager.list_all_docs(
            project=parse_multi(project), doc_type=parse_multi(doc_type), limit=limit, offset=offset,
        )

    @router.get("/docs/{doc_id}")
    def api_doc_detail(doc_id: int = Path(...)):
        doc = project_manager.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    @router.get("/docs/{doc_id}/md")
    def api_doc_md(doc_id: int = Path(...)):
        """Export a document as raw markdown."""
        doc = project_manager.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        title = doc.get("title") or "Untitled"
        content = doc.get("content", "")
        # Resolve cairn:// URLs to HTTP paths for portability
        import re
        content = re.sub(
            r'cairn://attachments/(\d+)/([^)\s"]+)',
            r'/api/attachments/\1/\2',
            content,
        )
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        filename = f"{safe_title.strip() or 'document'}.md"

        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/docs/{doc_id}/pdf")
    def api_doc_pdf(doc_id: int = Path(...)):
        """Export a document as PDF via server-side markdown→HTML→PDF."""
        import base64
        import re

        import markdown as md  # type: ignore[import-untyped]
        import weasyprint

        doc = project_manager.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        title = doc.get("title") or "Untitled"
        content = doc.get("content", "")

        html_body = md.markdown(
            content,
            extensions=["tables", "fenced_code", "toc", "sane_lists", "codehilite"],
            extension_configs={
                "codehilite": {"css_class": "codehilite", "guess_lang": False},
            },
        )

        # Resolve cairn://attachments/{id}/{filename} → inline data URIs
        def _resolve_cairn_img(match: re.Match) -> str:
            att_id = int(match.group(1))
            att = project_manager.get_attachment(att_id)
            if att is None:
                return match.group(0)  # leave as-is if not found
            b64 = base64.b64encode(att["data"]).decode()
            return f'src="data:{att["mime_type"]};base64,{b64}"'

        html_body = re.sub(
            r'src="cairn://attachments/(\d+)/[^"]*"',
            _resolve_cairn_img,
            html_body,
        )

        css = """
            @page {
                size: A4;
                margin: 2cm 2.2cm 2.5cm 2.2cm;
                @bottom-center {
                    content: counter(page);
                    font-size: 8pt;
                    color: #999;
                }
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                font-size: 10.5pt;
                line-height: 1.55;
                color: #1a1a1a;
                orphans: 2;
                widows: 2;
            }
            h1 {
                font-size: 22pt;
                font-weight: 700;
                color: #111;
                border-bottom: 2px solid #333;
                padding-bottom: 6pt;
                margin-top: 0;
                margin-bottom: 12pt;
            }
            h2 {
                font-size: 15pt;
                font-weight: 600;
                color: #222;
                margin-top: 22pt;
                margin-bottom: 8pt;
                page-break-after: avoid;
            }
            h3 {
                font-size: 12pt;
                font-weight: 600;
                color: #333;
                margin-top: 16pt;
                margin-bottom: 6pt;
                page-break-after: avoid;
            }
            h4, h5, h6 {
                font-size: 10.5pt;
                font-weight: 600;
                margin-top: 12pt;
                margin-bottom: 4pt;
            }
            p { margin: 0 0 8pt 0; }
            strong { font-weight: 600; }
            a { color: #1a56db; text-decoration: underline; }
            a[href^="http"]::after {
                content: " (" attr(href) ")";
                font-size: 0.8em;
                color: #666;
                word-break: break-all;
            }
            a[href^="cairn://"]::after,
            a[href^="data:"]::after { content: none; }
            hr {
                border: none;
                border-top: 1px solid #ddd;
                margin: 16pt 0;
            }
            ul, ol { margin: 0 0 8pt 0; padding-left: 22pt; }
            li { margin-bottom: 3pt; }
            li > ul, li > ol { margin-top: 3pt; margin-bottom: 0; }
            code {
                font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                font-size: 9pt;
                background: #f3f4f6;
                padding: 1pt 4pt;
                border-radius: 3pt;
                color: #d63384;
            }
            pre {
                background: #f8f9fa;
                border: 1px solid #e5e7eb;
                border-radius: 5pt;
                padding: 10pt 12pt;
                margin: 8pt 0 12pt 0;
                overflow-x: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                page-break-inside: avoid;
            }
            pre code {
                background: none;
                padding: 0;
                border-radius: 0;
                color: inherit;
                font-size: 8.5pt;
                line-height: 1.5;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 10pt 0 14pt 0;
                font-size: 9.5pt;
                page-break-inside: avoid;
            }
            th, td {
                border: 1px solid #d1d5db;
                padding: 6pt 10pt;
                text-align: left;
                vertical-align: top;
            }
            th {
                background: #f3f4f6;
                font-weight: 600;
                color: #374151;
            }
            tr:nth-child(even) td { background: #fafafa; }
            blockquote {
                border-left: 3pt solid #6366f1;
                margin: 10pt 0;
                padding: 8pt 14pt;
                background: #f5f3ff;
                color: #312e81;
                font-style: italic;
            }
            blockquote p { margin-bottom: 4pt; }
            blockquote p:last-child { margin-bottom: 0; }
            img {
                max-width: 100%;
                height: auto;
                border-radius: 4pt;
                margin: 8pt 0;
                page-break-inside: avoid;
            }
            .codehilite { background: #f8f9fa; padding: 0; }
        """

        html_doc = (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title>"
            f"<style>{css}</style></head><body>"
            f"{html_body}</body></html>"
        )

        pdf_bytes = weasyprint.HTML(string=html_doc).write_pdf()

        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        filename = f"{safe_title.strip() or 'document'}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/clusters/visualization")
    def api_cluster_visualization(
        project: str | None = Query(None),
    ):
        return cluster_engine.get_visualization(project=project)

    @router.get("/clusters")
    def api_clusters(
        project: str | None = Query(None),
        topic: str | None = Query(None),
        min_confidence: float = Query(0.5, ge=0.0, le=1.0),
        limit: int = Query(10, ge=1, le=100),
    ):
        stale = cluster_engine.is_stale(project)
        refreshing = False
        if stale:
            # Kick off background re-clustering instead of blocking the request
            refreshing = cluster_engine.run_clustering_background(project)
            if not refreshing:
                # Already running — just note it
                refreshing = cluster_engine.is_clustering_in_progress(project)

        clusters = cluster_engine.get_clusters(
            project=project,
            topic=topic,
            min_confidence=min_confidence,
            limit=limit,
        )
        result = {"cluster_count": len(clusters), "clusters": clusters}
        if stale:
            result["stale"] = True
            result["refreshing"] = refreshing
        return result

    @router.get("/rules")
    def api_rules(
        project: str | None = Query(None),
        limit: int | None = Query(None, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return memory_store.get_rules(parse_multi(project), limit=limit, offset=offset)

    @router.get("/graph")
    def api_graph(
        project: str | None = Query(None),
        relation_type: str | None = Query(None),
        min_importance: float = Query(0.0, ge=0.0, le=1.0),
    ):
        NODE_CAP = 500

        edge_where = ["m1.is_active = true", "m2.is_active = true"]
        edge_params: list = []

        if project:
            edge_where.append("(p1.name = %s OR p2.name = %s)")
            edge_params.extend([project, project])
        if relation_type:
            edge_where.append("mr.relation = %s")
            edge_params.append(relation_type)
        if min_importance > 0:
            edge_where.append("(m1.importance >= %s OR m2.importance >= %s)")
            edge_params.extend([min_importance, min_importance])

        edge_clause = " AND ".join(edge_where)

        edges_raw = db.execute(
            f"""
            SELECT mr.source_id, mr.target_id, mr.relation, mr.created_at
            FROM memory_relations mr
            JOIN memories m1 ON mr.source_id = m1.id
            JOIN memories m2 ON mr.target_id = m2.id
            LEFT JOIN projects p1 ON m1.project_id = p1.id
            LEFT JOIN projects p2 ON m2.project_id = p2.id
            WHERE {edge_clause}
            ORDER BY mr.created_at DESC
            LIMIT 2000
            """,
            tuple(edge_params),
        )

        node_ids: set[int] = set()
        edges = []
        for row in edges_raw:
            node_ids.add(row["source_id"])
            node_ids.add(row["target_id"])
            edges.append({
                "source": row["source_id"],
                "target": row["target_id"],
                "relation": row["relation"] or "related",
                "created_at": row["created_at"].isoformat(),
            })

        if not node_ids:
            return {
                "nodes": [],
                "edges": [],
                "stats": {"node_count": 0, "edge_count": 0, "relation_types": {}},
            }

        id_list = list(node_ids)
        if len(id_list) > NODE_CAP:
            placeholders = ",".join(["%s"] * len(id_list))
            top_nodes = db.execute(
                f"""
                SELECT id FROM memories
                WHERE id IN ({placeholders})
                ORDER BY importance DESC
                LIMIT %s
                """,
                tuple(id_list) + (NODE_CAP,),
            )
            id_list = [r["id"] for r in top_nodes]
            node_ids = set(id_list)
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

        placeholders = ",".join(["%s"] * len(id_list))
        nodes_raw = db.execute(
            f"""
            SELECT m.id, m.summary, m.memory_type, m.importance,
                   m.created_at, m.updated_at,
                   p.name as project,
                   c.id as cluster_id, c.label as cluster_label
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            LEFT JOIN cluster_members cm ON cm.memory_id = m.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            WHERE m.id IN ({placeholders})
            """,
            tuple(id_list),
        )

        now = datetime.now(UTC)
        nodes = []
        for r in nodes_raw:
            updated = r["updated_at"] if r["updated_at"] else r["created_at"]
            age_days = (now - updated).days if updated else 0
            size = 5 + float(r["importance"]) * 8
            node = {
                "id": r["id"],
                "summary": r["summary"] or f"Memory #{r['id']}",
                "memory_type": r["memory_type"],
                "importance": float(r["importance"]),
                "project": r["project"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": updated.isoformat() if updated else r["created_at"].isoformat(),
                "cluster_id": r["cluster_id"],
                "cluster_label": r["cluster_label"],
                "age_days": age_days,
                "size": round(size, 1),
            }
            nodes.append(node)

        relation_counts: dict[str, int] = {}
        for e in edges:
            rel = e["relation"]
            relation_counts[rel] = relation_counts.get(rel, 0) + 1

        relation_colors = {
            "extends": "#3b82f6",
            "contradicts": "#ef4444",
            "implements": "#22c55e",
            "depends_on": "#f59e0b",
            "related": "#6b7280",
        }

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "relation_types": relation_counts,
                "relation_colors": relation_colors,
            },
        }

    @router.get("/knowledge-graph")
    def api_knowledge_graph(
        project: str | None = Query(None),
        entity_type: str | None = Query(None),
        limit: int = Query(500, ge=1, le=2000),
    ):
        """Knowledge graph from Neo4j — entities as nodes, statement triples as edges."""
        project_id = None
        if project:
            project_id = get_project(db, project)
            if project_id is None:
                return {"nodes": [], "edges": [], "stats": {
                    "node_count": 0, "edge_count": 0, "entity_types": {},
                }}

        entity_types = [entity_type] if entity_type else None

        return graph_provider.get_knowledge_graph_visualization(  # type: ignore[attr-defined]
            project_id=project_id,
            entity_types=entity_types,
            limit=limit,
        )

    # --- Analysis ---

    @router.post("/consolidate")
    def api_consolidate(body: ConsolidateBody = Body(...)):
        consolidation_engine = svc.consolidation_engine
        return consolidation_engine.consolidate(body.project, dry_run=body.dry_run)

    @router.post("/orient")
    def api_orient(body: OrientBody = Body(...)):
        from cairn.core.orient import run_orient

        try:
            return run_orient(
                project=body.project,
                config=svc.config,
                db=db,
                memory_store=memory_store,
                search_engine=svc.search_engine,
                work_item_manager=svc.work_item_manager,
                graph_provider=graph_provider,
            )
        except Exception as e:
            logger.exception("orient failed")
            raise HTTPException(status_code=500, detail=f"Orient failed: {e}") from e

    # --- Project mutations ---

    @router.post("/projects/{name}/links")
    def api_link_project(name: str = Path(...), body: LinkProjectBody = Body(...)):
        try:
            return project_manager.link(name, body.target, body.link_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.patch("/projects/{name}/prefix")
    def api_update_prefix(name: str = Path(...), body: UpdatePrefixBody = Body(...)):
        try:
            return project_manager.update_prefix(name, body.prefix)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.patch("/docs/{doc_id}")
    def api_update_doc(doc_id: int = Path(...), body: UpdateDocBody = Body(...)):
        doc = project_manager.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return project_manager.update_doc(doc_id, body.content, title=body.title)
