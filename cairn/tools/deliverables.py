"""Deliverable tools: create, review, submit, synthesize deliverables."""

import logging

from cairn.core.constants import MAX_LIMIT
from cairn.core.services import Services
from cairn.tools.auth import check_project_access
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register deliverable-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def deliverables(
        action: str,
        work_item_id: int | str | None = None,
        project: str | None = None,
        description: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
        gate_type: str | None = None,
        actor: str | None = None,
        note: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict | list[dict]:
        """Deliverable management — structured outputs attached to work items.

        Actions (required params in parens):
        - 'get': Get deliverable for a work item (work_item_id).
        - 'create': Create a deliverable (work_item_id, description as summary). Optional: metadata for changes/decisions/open_items/metrics, status.
        - 'review': Approve/revise/reject (work_item_id, gate_type as action: approve/revise/reject). Optional: note, actor.
        - 'submit': Submit draft for review (work_item_id).
        - 'pending': List deliverables needing review. Optional: project, limit, offset.
        - 'synthesize': Create epic deliverable from child deliverables (work_item_id). Optional: description as summary override.
        - 'children': Collect latest deliverables from all children (work_item_id).
        """
        try:
            check_project_access(svc, project)

            def _do_deliverables():
                deliverable_manager = svc.deliverable_manager

                if action == "get":
                    if not work_item_id:
                        return {"error": "work_item_id is required for get"}
                    result = deliverable_manager.get(int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id)
                    return result or {"error": f"No deliverable found for work item {work_item_id}"}

                if action == "create":
                    if not work_item_id:
                        return {"error": "work_item_id is required for create"}
                    wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                    return deliverable_manager.create(
                        work_item_id=wi_id,
                        summary=description or "",
                        changes=metadata.get("changes") if metadata else None,
                        decisions=metadata.get("decisions") if metadata else None,
                        open_items=metadata.get("open_items") if metadata else None,
                        metrics=metadata.get("metrics") if metadata else None,
                        status=status or "draft",
                    )

                if action == "review":
                    if not work_item_id:
                        return {"error": "work_item_id is required for review"}
                    review_action = gate_type  # reuse gate_type param for review action
                    if review_action not in ("approve", "revise", "reject"):
                        return {"error": "gate_type must be 'approve', 'revise', or 'reject' for review"}
                    wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                    return deliverable_manager.review(
                        work_item_id=wi_id,
                        action=review_action,
                        reviewer=actor,
                        notes=note,
                    )

                if action == "submit":
                    if not work_item_id:
                        return {"error": "work_item_id is required for submit"}
                    wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                    return deliverable_manager.submit_for_review(wi_id)

                if action == "pending":
                    return deliverable_manager.list_pending(
                        project=project, limit=min(limit, MAX_LIMIT), offset=offset,
                    )

                if action == "synthesize":
                    if not work_item_id:
                        return {"error": "work_item_id (parent epic) is required for synthesize"}
                    wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                    return deliverable_manager.synthesize_epic(
                        wi_id, summary_override=description,
                    )

                if action == "children":
                    if not work_item_id:
                        return {"error": "work_item_id (parent) is required for children"}
                    wi_id = int(work_item_id) if isinstance(work_item_id, str) and work_item_id.isdigit() else work_item_id
                    return {"items": deliverable_manager.collect_child_deliverables(wi_id)}

                return {"error": f"Unknown action: {action}"}

            return await in_thread(svc.db, _do_deliverables)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("deliverables failed")
            return {"error": f"Internal error: {e}"}
