"""Knowledge graph entity and statement editing endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel

from cairn.core.services import Services
from cairn.core.utils import get_or_create_project, get_project
from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


class CreateEntityBody(BaseModel):
    name: str
    entity_type: str
    project: str


class UpdateEntityBody(BaseModel):
    name: str | None = None
    entity_type: str | None = None


class MergeEntitiesBody(BaseModel):
    canonical_id: str
    duplicate_id: str


def _require_graph(graph_provider: GraphProvider) -> GraphProvider:
    """Passthrough — Neo4j is always available (required dependency)."""
    return graph_provider


def register_routes(router: APIRouter, svc: Services, **kw):
    db = svc.db
    graph_provider = svc.graph_provider
    embedding = svc.embedding

    @router.get("/entities")
    def api_list_entities(
        project: str = Query(...),
        search: str | None = Query(None),
        entity_type: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
    ):
        graph = _require_graph(graph_provider)
        project_id = get_project(db, project)
        if project_id is None:
            return {"items": [], "total": 0}
        entities = graph.list_entities(
            project_id=project_id,
            search=search,
            entity_type=entity_type,
            limit=limit,
        )
        return {"items": entities, "total": len(entities)}

    @router.get("/entities/{entity_uuid}")
    def api_get_entity(entity_uuid: str = Path(...)):
        graph = _require_graph(graph_provider)
        entity = graph.get_entity(entity_uuid)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        # Also fetch statements
        statements = graph.find_entity_statements(entity_uuid)
        return {
            "uuid": entity.uuid,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "project_id": entity.project_id,
            "attributes": entity.attributes,
            "statements": [
                {
                    "uuid": s.uuid,
                    "fact": s.fact,
                    "aspect": s.aspect,
                    "episode_id": s.episode_id,
                    "valid_at": s.valid_at,
                    "invalid_at": s.invalid_at,
                }
                for s in statements
            ],
        }

    @router.post("/entities")
    def api_create_entity(body: CreateEntityBody):
        graph = _require_graph(graph_provider)
        project_id = get_or_create_project(db, body.project)
        name_embedding = embedding.embed(body.name)
        entity_uuid = graph.create_entity(
            name=body.name,
            entity_type=body.entity_type,
            embedding=name_embedding,
            project_id=project_id,
        )
        return {
            "uuid": entity_uuid,
            "name": body.name,
            "entity_type": body.entity_type,
            "project_id": project_id,
        }

    @router.patch("/entities/{entity_uuid}")
    def api_update_entity(entity_uuid: str = Path(...), body: UpdateEntityBody = Body(...)):
        graph = _require_graph(graph_provider)
        # Re-embed if name changed
        new_embedding = None
        if body.name:
            new_embedding = embedding.embed(body.name)
        found = graph.update_entity(
            entity_id=entity_uuid,
            name=body.name,
            entity_type=body.entity_type,
            embedding=new_embedding,
        )
        if not found:
            raise HTTPException(status_code=404, detail="Entity not found")
        entity = graph.get_entity(entity_uuid)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found after update")
        return {
            "uuid": entity.uuid,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "project_id": entity.project_id,
        }

    @router.delete("/entities/{entity_uuid}")
    def api_delete_entity(entity_uuid: str = Path(...)):
        graph = _require_graph(graph_provider)
        # Verify it exists first
        entity = graph.get_entity(entity_uuid)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        result = graph.delete_entity(entity_uuid)
        return result

    @router.post("/entities/merge")
    def api_merge_entities(body: MergeEntitiesBody):
        graph = _require_graph(graph_provider)
        # Verify both exist
        canonical = graph.get_entity(body.canonical_id)
        if not canonical:
            raise HTTPException(status_code=404, detail="Canonical entity not found")
        duplicate = graph.get_entity(body.duplicate_id)
        if not duplicate:
            raise HTTPException(status_code=404, detail="Duplicate entity not found")
        result = graph.merge_entities(body.canonical_id, body.duplicate_id)
        return result

    @router.get("/entities/{entity_uuid}/statements")
    def api_entity_statements(
        entity_uuid: str = Path(...),
        aspects: str | None = Query(None),
    ):
        graph = _require_graph(graph_provider)
        entity = graph.get_entity(entity_uuid)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        aspect_list = aspects.split(",") if aspects else None
        statements = graph.find_entity_statements(entity_uuid, aspects=aspect_list)
        return {
            "entity_uuid": entity_uuid,
            "statements": [
                {
                    "uuid": s.uuid,
                    "fact": s.fact,
                    "aspect": s.aspect,
                    "episode_id": s.episode_id,
                    "valid_at": s.valid_at,
                    "invalid_at": s.invalid_at,
                }
                for s in statements
            ],
        }

    @router.post("/statements/{statement_uuid}/invalidate")
    def api_invalidate_statement(
        statement_uuid: str = Path(...),
        invalidated_by: str = Query("user"),
    ):
        graph = _require_graph(graph_provider)
        try:
            graph.invalidate_statement(statement_uuid, invalidated_by=invalidated_by)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"invalidated": True, "uuid": statement_uuid}
