"""Beliefs REST API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Path, HTTPException
from pydantic import BaseModel

from cairn.core.services import Services


class CrystallizeRequest(BaseModel):
    content: str
    domain: str | None = None
    confidence: float = 0.7
    evidence_ids: list[int] | None = None
    agent_name: str | None = None
    provenance: str = "crystallized"


class ChallengeRequest(BaseModel):
    evidence_id: int | None = None
    reason: str | None = None
    confidence_delta: float = -0.1


class RetractRequest(BaseModel):
    reason: str | None = None


def register_routes(router: APIRouter, svc: Services, **kw):
    bs = svc.belief_store
    if not bs:
        return

    @router.get("/beliefs")
    def api_beliefs_list(
        project: str = Query(...),
        agent_name: str | None = Query(None),
        domain: str | None = Query(None),
        status: str = Query("active"),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return bs.list_beliefs(
            project, agent_name=agent_name, domain=domain,
            status=status, limit=limit, offset=offset,
        )

    @router.get("/beliefs/{belief_id}")
    def api_belief_detail(belief_id: int = Path(...)):
        result = bs.get(belief_id)
        if not result:
            raise HTTPException(status_code=404, detail="Belief not found")
        return result

    @router.post("/beliefs")
    def api_belief_crystallize(
        project: str = Query(...),
        body: CrystallizeRequest = ...,
    ):
        return bs.crystallize(
            project, body.content,
            domain=body.domain, confidence=body.confidence,
            evidence_ids=body.evidence_ids, agent_name=body.agent_name,
            provenance=body.provenance,
        )

    @router.patch("/beliefs/{belief_id}/challenge")
    def api_belief_challenge(
        belief_id: int = Path(...),
        body: ChallengeRequest = ...,
    ):
        result = bs.challenge(
            belief_id,
            evidence_id=body.evidence_id,
            reason=body.reason,
            confidence_delta=body.confidence_delta,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @router.patch("/beliefs/{belief_id}/retract")
    def api_belief_retract(
        belief_id: int = Path(...),
        body: RetractRequest = ...,
    ):
        result = bs.retract(belief_id, reason=body.reason)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
