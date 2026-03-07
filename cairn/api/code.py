"""Code intelligence endpoints — query and arch-check.

Indexing is handled by the standalone code worker (python -m cairn.code),
not by the server. The server only queries the pre-built graph.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from cairn.core.services import Services

logger = logging.getLogger(__name__)


class CodeQueryBody(BaseModel):
    action: str
    project: str
    target: str = ""
    query: str = ""
    kind: str = ""
    depth: int = 3
    limit: int = 20


class ArchCheckBody(BaseModel):
    project: str
    path: str = ""
    config_path: str = ""
    use_graph: bool = False


def register_routes(router: APIRouter, svc: Services, **kw):
    from cairn.core.code_ops import (
        run_arch_check,
        run_code_query,
    )

    @router.post("/code/query")
    def api_code_query(body: CodeQueryBody = Body(...)):
        try:
            return run_code_query(
                action=body.action,
                project=body.project,
                target=body.target,
                query=body.query,
                kind=body.kind,
                depth=body.depth,
                limit=body.limit,
                graph_provider=svc.graph_provider,
                db=svc.db,
                config=svc.config,
                embedding_engine=svc.embedding,
            )
        except Exception as e:
            logger.exception("code_query failed")
            raise HTTPException(status_code=500, detail=f"Code query failed: {e}") from e

    @router.post("/code/arch-check")
    def api_arch_check(body: ArchCheckBody = Body(...)):
        try:
            return run_arch_check(
                project=body.project,
                path=body.path,
                config_path=body.config_path,
                use_graph=body.use_graph,
                graph_provider=svc.graph_provider,
                db=svc.db,
                config=svc.config,
                project_manager=svc.project_manager,
            )
        except Exception as e:
            logger.exception("arch_check failed")
            raise HTTPException(status_code=500, detail=f"Architecture check failed: {e}") from e
