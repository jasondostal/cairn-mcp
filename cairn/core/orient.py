"""Shared orient + trail logic for both MCP and REST transports.

Extracted from server.py so both transports call identical code.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from cairn.core.budget import apply_list_budget, estimate_tokens_for_dict
from cairn.core.constants import (
    BUDGET_RULES_PER_ITEM,
    BUDGET_SEARCH_PER_ITEM,
    ORIENT_ALLOC_LEARNINGS,
    ORIENT_ALLOC_RULES,
    ORIENT_ALLOC_TRAIL,
    ORIENT_ALLOC_WORK_ITEMS,
    ORIENT_ALLOC_WORKING_MEMORY,
)

logger = logging.getLogger(__name__)


def fetch_trail_data(
    *,
    db: Any,
    graph_provider: Any | None = None,
    project: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> dict:
    """Fetch recent activity trail data.

    Merges two data sources following the HA philosophy:
    - PG (always): source of truth for what memories exist
    - Graph (when available): enriches with entity types and facts
    Neither source can suppress the other.
    """
    if not since:
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    project_id = None
    if project:
        from cairn.core.utils import get_project
        project_id = get_project(db, project)

    # --- PRIMARY: PG-based trail (always runs) ---
    rows = db.execute(
        """
        SELECT m.id, m.session_name, m.memory_type, m.importance,
               m.summary, m.entities, m.created_at, p.name AS project
        FROM memories m
        LEFT JOIN projects p ON m.project_id = p.id
        WHERE m.is_active = true AND m.created_at > %s
        """
        + (" AND m.project_id = %s" if project_id else "")
        + " ORDER BY m.created_at DESC LIMIT %s",
        (since,) + ((project_id,) if project_id else ()) + (limit,),
    )

    sessions: dict[str, dict] = {}
    for r in rows:
        sn = r["session_name"] or "no-session"
        if sn not in sessions:
            ts = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
            sessions[sn] = {
                "session_name": sn,
                "entities_touched": set(),
                "key_facts": [],
                "time_range": {"earliest": ts, "latest": ts},
            }
        s = sessions[sn]
        for entity in (r.get("entities") or []):
            s["entities_touched"].add(entity)
        if len(s["key_facts"]) < 5:
            summary = r.get("summary") or ""
            if summary:
                s["key_facts"].append(summary)
        ts = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
        if ts < s["time_range"]["earliest"]:
            s["time_range"]["earliest"] = ts
        if ts > s["time_range"]["latest"]:
            s["time_range"]["latest"] = ts

    # Convert sets to sorted lists for JSON serialization
    for s in sessions.values():
        s["entities_touched"] = sorted(s["entities_touched"])

    source = "memory"

    # --- ENRICHMENT: Graph data when available (non-blocking) ---
    if graph_provider:
        try:
            activity = graph_provider.recent_activity(
                project_id=project_id, since=since, limit=limit,
            )
            if activity:
                episode_ids = list({a["episode_id"] for a in activity if a.get("episode_id")})
                ep_session_map = {}
                if episode_ids:
                    placeholders = ",".join(["%s"] * len(episode_ids))
                    ep_rows = db.execute(
                        f"SELECT id, session_name FROM memories WHERE id IN ({placeholders})",
                        tuple(episode_ids),
                    )
                    ep_session_map = {r["id"]: r["session_name"] for r in ep_rows}

                for a in activity:
                    sn = ep_session_map.get(a.get("episode_id"), "unknown")
                    if sn in sessions:
                        s = sessions[sn]
                        if a.get("subject_name"):
                            s["entities_touched"].add(a["subject_name"])
                        if a.get("object_name"):
                            s["entities_touched"].add(a["object_name"])
                        if a.get("fact") and len(s["key_facts"]) < 5:
                            s["key_facts"].append(a["fact"])

                for s in sessions.values():
                    if isinstance(s["entities_touched"], set):
                        s["entities_touched"] = sorted(s["entities_touched"])

                source = "memory+graph"
        except Exception:
            logger.debug("Graph trail enrichment failed (non-blocking)", exc_info=True)

    result = {
        "source": source,
        "since": since,
        "sessions": list(sessions.values())[:10],
    }

    # --- ENRICHMENT: Thinking activity from graph (non-blocking) ---
    if graph_provider:
        try:
            thinking_activity = graph_provider.recent_thinking_activity(
                project_id=project_id, since=since, limit=10,
            )
            if thinking_activity:
                result["thinking"] = [
                    {
                        "type": "thinking",
                        "goal": t.get("goal", ""),
                        "status": t.get("status", ""),
                        "thought_count": t.get("thought_count", 0),
                        "created_at": t.get("created_at", ""),
                    }
                    for t in thinking_activity
                ]
        except Exception:
            logger.debug("Thinking trail failed", exc_info=True)

    return result


def run_orient(
    *,
    project: str | None = None,
    config: Any,
    db: Any,
    memory_store: Any,
    search_engine: Any,
    work_item_manager: Any,
    task_manager: Any,
    graph_provider: Any | None = None,
    working_memory_store: Any | None = None,
    belief_store: Any | None = None,
) -> dict:
    """Single-pass session boot. Returns rules, trail, learnings, and work items.

    Budget-driven: each section gets a token allocation with surplus flowing
    to the next section.
    """
    total_budget = config.budget.orient
    budget_rules = int(total_budget * ORIENT_ALLOC_RULES)
    budget_learnings = int(total_budget * ORIENT_ALLOC_LEARNINGS)
    budget_trail = int(total_budget * ORIENT_ALLOC_TRAIL)
    budget_working_memory = int(total_budget * ORIENT_ALLOC_WORKING_MEMORY)
    budget_work_items = int(total_budget * ORIENT_ALLOC_WORK_ITEMS)

    tokens_used = 0

    # --- Section 1: Rules (30%) ---
    rules_data: list[dict] = []
    try:
        result = memory_store.get_rules(project)
        rules_items = result.get("items", [])
        if rules_items:
            rules_data, rules_meta = apply_list_budget(
                rules_items, budget_rules, "content",
                per_item_max=BUDGET_RULES_PER_ITEM,
                overflow_message="...{omitted} more rules omitted.",
            )
            if rules_meta["omitted"] > 0:
                rules_data.append({"_overflow": rules_meta["overflow_message"]})
            rules_tokens = estimate_tokens_for_dict(rules_data)
            tokens_used += rules_tokens
            surplus = max(0, budget_rules - rules_tokens)
        else:
            surplus = budget_rules
        budget_learnings += surplus
    except Exception:
        logger.debug("orient: rules section failed", exc_info=True)
        budget_learnings += budget_rules

    # --- Section 2: Learnings (25% + surplus) ---
    learnings_data: list[dict] = []
    try:
        learnings_results = search_engine.search(
            query="learning",
            project=project,
            memory_type="learning",
            search_mode="semantic",
            limit=5,
            include_full=True,
        )
        if learnings_results:
            learnings_data, learnings_meta = apply_list_budget(
                learnings_results, budget_learnings, "content",
                per_item_max=BUDGET_SEARCH_PER_ITEM,
                overflow_message="...{omitted} more learnings omitted.",
            )
            if learnings_meta["omitted"] > 0:
                learnings_data.append({"_overflow": learnings_meta["overflow_message"]})
            learnings_tokens = estimate_tokens_for_dict(learnings_data)
            tokens_used += learnings_tokens
            surplus = max(0, budget_learnings - learnings_tokens)
        else:
            surplus = budget_learnings
        budget_trail += surplus
    except Exception:
        logger.debug("orient: learnings section failed", exc_info=True)
        budget_trail += budget_learnings

    # --- Section 3: Trail (25% + surplus) ---
    trail_data = {}
    try:
        trail_data = fetch_trail_data(
            db=db, graph_provider=graph_provider,
            project=project, limit=20,
        )
        trail_tokens = estimate_tokens_for_dict(trail_data)
        if budget_trail > 0 and trail_tokens > budget_trail:
            for s in trail_data.get("sessions", []):
                if "key_facts" in s:
                    s["key_facts"] = s["key_facts"][:3]
            trail_data["sessions"] = trail_data.get("sessions", [])[:5]
            trail_tokens = estimate_tokens_for_dict(trail_data)
        tokens_used += trail_tokens
        surplus = max(0, budget_trail - trail_tokens)
        budget_working_memory += surplus
    except Exception:
        logger.debug("orient: trail section failed", exc_info=True)
        budget_working_memory += budget_trail

    # --- Section 3.5: Working Memory (10% + surplus) ---
    working_memory_data: list[dict] = []
    if working_memory_store and project:
        try:
            wm_items = working_memory_store.orient_items(project, limit=5)
            if wm_items:
                working_memory_data, wm_meta = apply_list_budget(
                    wm_items, budget_working_memory, "content",
                    overflow_message="...{omitted} more active thoughts omitted.",
                )
                if wm_meta["omitted"] > 0:
                    working_memory_data.append({"_overflow": wm_meta["overflow_message"]})
                wm_tokens = estimate_tokens_for_dict(working_memory_data)
                tokens_used += wm_tokens
                surplus = max(0, budget_working_memory - wm_tokens)
            else:
                surplus = budget_working_memory
            budget_work_items += surplus
        except Exception:
            logger.debug("orient: working memory section failed", exc_info=True)
            budget_work_items += budget_working_memory
    else:
        budget_work_items += budget_working_memory

    # --- Section 3.6: Beliefs (compact, no budget — max 5 items) ---
    beliefs_data = []
    if belief_store and project:
        try:
            beliefs_data = belief_store.orient_beliefs(project, limit=5)
        except Exception:
            logger.debug("orient: beliefs section failed", exc_info=True)

    # --- Section 4: Work Items (18% + surplus) ---
    work_items_data = []
    try:
        if project:
            wi_ready = work_item_manager.ready_queue(project, limit=10)
            wi_active = work_item_manager.list_items(
                project=project, status="in_progress", limit=10,
            )
            wi_items = []
            for item in wi_ready.get("items", []):
                wi_items.append({
                    "display_id": item.get("display_id", ""),
                    "title": item.get("title", ""),
                    "priority": item.get("priority", 0),
                    "item_type": item.get("item_type", "task"),
                    "status": "ready",
                })
            for item in wi_active.get("items", []):
                wi_items.append({
                    "display_id": item.get("display_id", ""),
                    "title": item.get("title", ""),
                    "assignee": item.get("assignee"),
                    "item_type": item.get("item_type", "task"),
                    "status": "in_progress",
                })
            if wi_items:
                work_items_data = wi_items
            else:
                tasks_result = task_manager.list_tasks(project, include_completed=False)
                work_items_data = tasks_result.get("items", [])
        if work_items_data:
            content_key = "title" if work_items_data and "title" in work_items_data[0] else "description"
            work_items_data, wi_meta = apply_list_budget(
                work_items_data, budget_work_items, content_key,
                overflow_message="...{omitted} more work items omitted.",
            )
            if wi_meta["omitted"] > 0:
                work_items_data.append({"_overflow": wi_meta["overflow_message"]})
            tokens_used += estimate_tokens_for_dict(work_items_data)
    except Exception:
        logger.debug("orient: work items section failed", exc_info=True)

    return {
        "project": project,
        "rules": rules_data,
        "trail": trail_data,
        "learnings": learnings_data,
        "working_memory": working_memory_data,
        "beliefs": beliefs_data,
        "work_items": work_items_data,
        "_budget": {"total": total_budget, "used": tokens_used},
    }
