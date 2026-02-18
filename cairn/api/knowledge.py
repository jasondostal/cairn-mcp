"""Knowledge endpoints — projects, docs, clusters, rules, graph."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Path, HTTPException

from cairn.api.utils import parse_multi
from cairn.core.services import Services
from cairn.core.utils import get_project


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
        if cluster_engine.is_stale(project):
            cluster_engine.run_clustering(project)

        clusters = cluster_engine.get_clusters(
            project=project,
            topic=topic,
            min_confidence=min_confidence,
            limit=limit,
        )
        return {"cluster_count": len(clusters), "clusters": clusters}

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

        now = datetime.now(timezone.utc)
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
        if not graph_provider:
            raise HTTPException(
                status_code=503,
                detail="Knowledge graph not available (Neo4j not configured)",
            )

        project_id = None
        if project:
            project_id = get_project(db, project)
            if project_id is None:
                return {"nodes": [], "edges": [], "stats": {
                    "node_count": 0, "edge_count": 0, "entity_types": {},
                }}

        entity_types = [entity_type] if entity_type else None

        return graph_provider.get_knowledge_graph_visualization(
            project_id=project_id,
            entity_types=entity_types,
            limit=limit,
        )
