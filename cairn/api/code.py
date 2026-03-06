"""Code intelligence endpoints — index, query, describe, arch-check."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from cairn.core.services import Services

logger = logging.getLogger(__name__)


class CodeIndexBody(BaseModel):
    project: str
    path: str
    force: bool = False


class CodeQueryBody(BaseModel):
    action: str
    project: str
    target: str = ""
    query: str = ""
    kind: str = ""
    depth: int = 3
    limit: int = 20
    mode: str = "fulltext"


class CodeDescribeBody(BaseModel):
    project: str
    target: str = ""
    kind: str = ""
    limit: int = 50


class ArchCheckBody(BaseModel):
    project: str
    path: str = ""
    config_path: str = ""
    use_graph: bool = False


def register_routes(router: APIRouter, svc: Services, **kw):
    from cairn.core.code_ops import (
        run_arch_check,
        run_code_describe,
        run_code_index,
        run_code_query,
    )

    @router.post("/code/index")
    def api_code_index(body: CodeIndexBody = Body(...)):
        try:
            return run_code_index(
                project=body.project,
                path=body.path,
                force=body.force,
                graph_provider=svc.graph_provider,
                db=svc.db,
                config=svc.config,
            )
        except Exception as e:
            logger.exception("code_index failed")
            raise HTTPException(status_code=500, detail=f"Code index failed: {e}") from e

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
                mode=body.mode,
                graph_provider=svc.graph_provider,
                db=svc.db,
                config=svc.config,
                embedding_engine=svc.embedding,
            )
        except Exception as e:
            logger.exception("code_query failed")
            raise HTTPException(status_code=500, detail=f"Code query failed: {e}") from e

    @router.post("/code/describe")
    def api_code_describe(body: CodeDescribeBody = Body(...)):
        try:
            return run_code_describe(
                project=body.project,
                target=body.target,
                kind=body.kind,
                limit=body.limit,
                graph_provider=svc.graph_provider,
                db=svc.db,
                config=svc.config,
                llm=svc.llm,
                embedding_engine=svc.embedding,
            )
        except Exception as e:
            logger.exception("code_describe failed")
            raise HTTPException(status_code=500, detail=f"Code describe failed: {e}") from e

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
