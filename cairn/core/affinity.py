"""Affinity routing — match work to agents with relevant context (ca-157).

Scores candidate agents against a work item to find the best match.
Considers:
- Project familiarity: has the agent worked in this project before?
- File affinity: has the agent recently modified the same files?
- Capability match: does the agent have the required capabilities?
- Current load: how many active items is the agent already working on?
- Risk tier compatibility: can the agent handle this risk level?

Returns ranked agent suggestions for the ready queue and dispatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from cairn.core.agents import AgentDefinition, AgentRegistry, validate_dispatch
from cairn.core.antipatterns import extract_file_paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AffinityScore:
    """Scored agent-to-work-item affinity."""

    agent_name: str
    score: float  # 0.0 to 1.0
    reasons: tuple[str, ...] = ()
    disqualified: bool = False
    disqualify_reason: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "agent_name": self.agent_name,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
        }
        if self.disqualified:
            d["disqualified"] = True
            d["disqualify_reason"] = self.disqualify_reason
        return d


# Weight configuration for affinity scoring
WEIGHTS = {
    "project_familiarity": 0.25,
    "file_affinity": 0.30,
    "capability_match": 0.20,
    "low_load": 0.15,
    "risk_compatible": 0.10,
}


def score_agent(
    agent_def: AgentDefinition,
    work_item: dict,
    *,
    agent_history: list[dict] | None = None,
    active_items_count: int = 0,
    max_concurrent: int = 3,
) -> AffinityScore:
    """Score how well an agent matches a work item.

    Args:
        agent_def: The agent definition to evaluate.
        work_item: Work item dict with keys like project, title, description,
                   item_type, risk_tier.
        agent_history: List of previously completed work items by this agent.
                       Each dict should have: project, title, description.
        active_items_count: How many items this agent is currently working on.
        max_concurrent: Maximum concurrent items before penalizing.

    Returns:
        AffinityScore with composite score and explanation.
    """
    # Hard disqualifiers first
    errors = validate_dispatch(agent_def, work_item)
    if errors:
        return AffinityScore(
            agent_name=agent_def.name,
            score=0.0,
            disqualified=True,
            disqualify_reason="; ".join(errors),
        )

    scores: dict[str, float] = {}
    reasons: list[str] = []
    history = agent_history or []

    # 1. Project familiarity
    work_project = work_item.get("project", "")
    project_matches = sum(1 for h in history if h.get("project") == work_project)
    if project_matches > 0:
        # Diminishing returns: 1 item = 0.5, 2 = 0.75, 3+ = 1.0
        scores["project_familiarity"] = min(1.0, 0.25 + project_matches * 0.25)
        reasons.append(f"worked on {project_matches} item(s) in '{work_project}'")
    else:
        scores["project_familiarity"] = 0.0

    # 2. File affinity
    work_desc = f"{work_item.get('title', '')} {work_item.get('description', '')}"
    work_files = extract_file_paths(work_desc)
    if work_files:
        history_files: set[str] = set()
        for h in history:
            h_desc = f"{h.get('title', '')} {h.get('description', '')}"
            history_files.update(extract_file_paths(h_desc))

        if history_files:
            overlap = work_files & history_files
            if overlap:
                scores["file_affinity"] = min(1.0, len(overlap) / len(work_files))
                reasons.append(f"familiar with {len(overlap)}/{len(work_files)} file(s)")
            else:
                scores["file_affinity"] = 0.0
        else:
            scores["file_affinity"] = 0.0
    else:
        # No file paths in work item — neutral
        scores["file_affinity"] = 0.5

    # 3. Capability match
    # Infer required capabilities from work item type
    required_caps = _infer_capabilities(work_item)
    if required_caps and agent_def.capabilities:
        matched = sum(1 for c in required_caps if c in agent_def.capabilities)
        scores["capability_match"] = matched / len(required_caps)
        if matched < len(required_caps):
            missing = [c for c in required_caps if c not in agent_def.capabilities]
            reasons.append(f"missing capabilities: {', '.join(missing)}")
        else:
            reasons.append("all required capabilities present")
    else:
        scores["capability_match"] = 1.0  # No restrictions = full match

    # 4. Load factor
    if active_items_count >= max_concurrent:
        scores["low_load"] = 0.0
        reasons.append(f"at capacity ({active_items_count}/{max_concurrent})")
    elif active_items_count == 0:
        scores["low_load"] = 1.0
        reasons.append("idle")
    else:
        scores["low_load"] = 1.0 - (active_items_count / max_concurrent)
        reasons.append(f"working on {active_items_count} item(s)")

    # 5. Risk tier compatibility
    work_risk = work_item.get("risk_tier")
    if agent_def.max_risk_tier is not None and work_risk is not None:
        if work_risk < agent_def.max_risk_tier:
            scores["risk_compatible"] = 0.0
            reasons.append(f"risk tier {work_risk} exceeds agent max {agent_def.max_risk_tier}")
        else:
            scores["risk_compatible"] = 1.0
    else:
        scores["risk_compatible"] = 1.0

    # Weighted composite
    total = sum(scores.get(k, 0) * w for k, w in WEIGHTS.items())

    return AffinityScore(
        agent_name=agent_def.name,
        score=total,
        reasons=tuple(reasons),
    )


def rank_agents(
    registry: AgentRegistry,
    work_item: dict,
    *,
    agent_histories: dict[str, list[dict]] | None = None,
    active_counts: dict[str, int] | None = None,
    max_concurrent: int = 3,
) -> list[AffinityScore]:
    """Rank all registered agents for a work item.

    Returns scores sorted by score descending. Disqualified agents appear
    at the end with score 0.
    """
    histories = agent_histories or {}
    counts = active_counts or {}

    scores: list[AffinityScore] = []
    for agent_def in registry.list():
        s = score_agent(
            agent_def,
            work_item,
            agent_history=histories.get(agent_def.name, []),
            active_items_count=counts.get(agent_def.name, 0),
            max_concurrent=max_concurrent,
        )
        scores.append(s)

    # Sort: qualified first (by score desc), then disqualified
    scores.sort(key=lambda s: (not s.disqualified, s.score), reverse=True)
    return scores


def suggest_agent(
    registry: AgentRegistry,
    work_item: dict,
    **kwargs,
) -> AffinityScore | None:
    """Suggest the best agent for a work item.

    Returns the top-scoring non-disqualified agent, or None if all are
    disqualified.
    """
    ranked = rank_agents(registry, work_item, **kwargs)
    for s in ranked:
        if not s.disqualified:
            return s
    return None


def _infer_capabilities(work_item: dict) -> list[str]:
    """Infer required capabilities from work item characteristics."""
    item_type = work_item.get("item_type", "task")
    caps: list[str] = []

    if item_type == "epic":
        caps.extend(["dispatch_agents", "create_work_items"])
    elif item_type in ("task", "subtask"):
        caps.extend(["read_files", "write_files", "execute_code"])

    return caps
