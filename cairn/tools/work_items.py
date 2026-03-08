"""Work item and task tools."""

import logging

from cairn.core.constants import (
    MAX_LIMIT,
)
from cairn.core.resource_lock import lock_manager
from cairn.core.services import Services
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register work-item-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def work_items(
        action: str,
        project: str | None = None,
        title: str | None = None,
        description: str | None = None,
        item_type: str | None = None,
        priority: int | None = None,
        parent_id: int | None = None,
        work_item_id: int | str | None = None,
        blocker_id: int | str | None = None,
        blocked_id: int | str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        session_name: str | None = None,
        metadata: dict | None = None,
        acceptance_criteria: str | None = None,
        memory_ids: list[int] | None = None,
        include_children: bool = False,
        limit: int = 20,
        offset: int = 0,
        gate_type: str | None = None,
        gate_data: dict | None = None,
        gate_response: dict | None = None,
        risk_tier: int | None = None,
        constraints: dict | None = None,
        actor: str | None = None,
        note: str | None = None,
    ) -> dict | list[dict]:
        """Work tracking with hierarchy, dependencies, and agent dispatch.

        Actions (required params in parens):
        - 'create': New item (project, title). Optional: description, item_type, priority, risk_tier, constraints.
        - 'update': Modify fields (work_item_id). Any field can be updated.
        - 'list': Filtered list. Optional: project, status, item_type, assignee, limit, offset.
        - 'get': Full detail (work_item_id).
        - 'complete': Mark done + auto-unblock dependents (work_item_id).
        - 'claim': Assign to agent/person (work_item_id, assignee).
        - 'add_child': Add subtask (work_item_id as parent, title).
        - 'block'/'unblock': Manage dependencies (blocker_id, blocked_id).
        - 'ready': Dispatch queue — unblocked, unassigned items (project).
        - 'link_memories': Attach context (work_item_id, memory_ids).
        - 'set_gate': Block on human input (work_item_id, gate_type). Optional: gate_data, actor.
        - 'resolve_gate': Unblock (work_item_id). Optional: gate_response, actor.
        - 'heartbeat': Agent progress (work_item_id, assignee). Optional: state, note.
        - 'activity': History log (work_item_id).
        - 'briefing': Agent dispatch context (work_item_id).
        - 'decompose': Epic decomposition context — briefing + existing children (work_item_id).
        - 'progress': Subtask progress summary — status counts, stale agents, blocked items (work_item_id).
        - 'analyze': Anti-pattern detection on epic children — Split Keel, Drifting Anchorage, Skeleton Crew (work_item_id).
        - 'gated': Items awaiting gates. Optional: project, gate_type.

        See also: deliverables(), locks(), suggest_agent() for actions moved to dedicated tools.
        """
        try:
            def _do_work_items():
                work_item_manager = svc.work_item_manager

                if action == "create":
                    if not project or not title:
                        return {"error": "project and title are required for create"}
                    return work_item_manager.create(
                        project=project, title=title, description=description,
                        item_type=item_type or "task", priority=priority or 0,
                        parent_id=parent_id, session_name=session_name,
                        metadata=metadata, acceptance_criteria=acceptance_criteria,
                        constraints=constraints, risk_tier=risk_tier,
                    )

                if action == "update":
                    if not work_item_id:
                        return {"error": "work_item_id is required for update"}
                    fields = {}
                    if session_name is not None:
                        fields["_calling_session"] = session_name
                    if title is not None:
                        fields["title"] = title
                    if description is not None:
                        fields["description"] = description
                    if status is not None:
                        fields["status"] = status
                    if priority is not None:
                        fields["priority"] = priority
                    if assignee is not None:
                        fields["assignee"] = assignee
                    if acceptance_criteria is not None:
                        fields["acceptance_criteria"] = acceptance_criteria
                    if item_type is not None:
                        fields["item_type"] = item_type
                    if session_name is not None:
                        fields["session_name"] = session_name
                    if metadata is not None:
                        fields["metadata"] = metadata
                    if risk_tier is not None:
                        fields["risk_tier"] = risk_tier
                    if constraints is not None:
                        fields["constraints"] = constraints
                    if parent_id is not None:
                        fields["parent_id"] = parent_id
                    return work_item_manager.update(work_item_id, **fields)

                if action == "claim":
                    if not work_item_id or not assignee:
                        return {"error": "work_item_id and assignee are required for claim"}
                    return work_item_manager.claim(work_item_id, assignee, session_name=session_name)

                if action == "complete":
                    if not work_item_id:
                        return {"error": "work_item_id is required for complete"}
                    result = work_item_manager.complete(work_item_id, session_name=session_name)
                    # Auto-release locks held by this work item (ca-156)
                    if project:
                        released = lock_manager.release(
                            project, work_item_id=str(work_item_id),
                        )
                        if released:
                            result["locks_released"] = released
                    return result

                if action == "add_child":
                    if not work_item_id or not title:
                        return {"error": "work_item_id (parent) and title are required for add_child"}
                    return work_item_manager.add_child(
                        parent_id=work_item_id, title=title, description=description,
                        priority=priority or 0, session_name=session_name,
                        metadata=metadata, acceptance_criteria=acceptance_criteria,
                        constraints=constraints, risk_tier=risk_tier,
                    )

                if action == "block":
                    if not blocker_id or not blocked_id:
                        return {"error": "blocker_id and blocked_id are required for block"}
                    return work_item_manager.block(blocker_id, blocked_id)

                if action == "unblock":
                    if not blocker_id or not blocked_id:
                        return {"error": "blocker_id and blocked_id are required for unblock"}
                    return work_item_manager.unblock(blocker_id, blocked_id)

                if action == "list":
                    return work_item_manager.list_items(
                        project=project, status=status, item_type=item_type,
                        assignee=assignee, parent_id=parent_id,
                        include_children=include_children,
                        limit=min(limit, MAX_LIMIT), offset=offset,
                    )

                if action == "ready":
                    if not project:
                        return {"error": "project is required for ready"}
                    return work_item_manager.ready_queue(project, limit=min(limit, MAX_LIMIT))

                if action == "get":
                    if not work_item_id:
                        return {"error": "work_item_id is required for get"}
                    return work_item_manager.get(work_item_id)

                if action == "link_memories":
                    if not work_item_id or not memory_ids:
                        return {"error": "work_item_id and memory_ids are required for link_memories"}
                    return work_item_manager.link_memories(work_item_id, memory_ids)

                if action == "set_gate":
                    if not work_item_id or not gate_type:
                        return {"error": "work_item_id and gate_type are required for set_gate"}
                    return work_item_manager.set_gate(
                        work_item_id, gate_type, gate_data=gate_data, actor=actor,
                    )

                if action == "resolve_gate":
                    if not work_item_id:
                        return {"error": "work_item_id is required for resolve_gate"}
                    return work_item_manager.resolve_gate(
                        work_item_id, response=gate_response, actor=actor,
                    )

                if action == "heartbeat":
                    if not work_item_id or not assignee:
                        return {"error": "work_item_id and assignee are required for heartbeat"}
                    return work_item_manager.heartbeat(
                        work_item_id, assignee, state=status or "working", note=note,
                        session_name=session_name,
                    )

                if action == "activity":
                    if not work_item_id:
                        return {"error": "work_item_id is required for activity"}
                    return work_item_manager.get_activity(
                        work_item_id, limit=min(limit, MAX_LIMIT), offset=offset,
                    )

                if action == "briefing":
                    if not work_item_id:
                        return {"error": "work_item_id is required for briefing"}
                    return work_item_manager.generate_briefing(work_item_id)

                if action == "decompose":
                    if not work_item_id:
                        return {"error": "work_item_id is required for decompose"}
                    return work_item_manager.decomposition_context(work_item_id)

                if action == "progress":
                    if not work_item_id:
                        return {"error": "work_item_id is required for progress"}
                    return work_item_manager.progress_summary(work_item_id)

                if action == "analyze":
                    if not work_item_id:
                        return {"error": "work_item_id (parent) is required for analyze"}
                    from cairn.core.antipatterns import analyze_epic
                    decomp = work_item_manager.decomposition_context(work_item_id)
                    return analyze_epic(
                        decomp.get("existing_children", []),
                        original_count=metadata.get("original_count") if metadata else None,
                    )

                if action == "gated":
                    return work_item_manager.gated_items(
                        project=project, gate_type=gate_type, limit=min(limit, MAX_LIMIT),
                    )

                return {"error": f"Unknown action: {action}"}

            return await in_thread(svc.db, _do_work_items)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("work_items failed")
            return {"error": f"Internal error: {e}"}
