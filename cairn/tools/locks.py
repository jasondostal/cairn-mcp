"""Resource lock tools: acquire, release, check, and list file locks."""

import logging

from cairn.core.resource_lock import lock_manager
from cairn.core.services import Services
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register resource-lock tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def locks(
        action: str,
        project: str | None = None,
        work_item_id: int | str | None = None,
        assignee: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Resource locking — prevent file conflicts between concurrent agents.

        Actions (required params in parens):
        - 'acquire': Acquire file locks (project, assignee). metadata.paths = list of file paths. Optional: work_item_id.
        - 'release': Release file locks (project). Provide work_item_id or assignee or metadata.paths.
        - 'check': Check for conflicts (project). metadata.paths = list of paths. Optional: assignee.
        - 'list': List active locks (project). Optional: assignee, work_item_id.
        """
        try:
            def _do_locks():
                if action == "acquire":
                    if not project:
                        return {"error": "project is required for acquire"}
                    paths = (metadata or {}).get("paths")
                    if not paths or not isinstance(paths, list):
                        return {"error": "metadata.paths (list of file paths) is required for acquire"}
                    owner = assignee or "unknown"
                    wi_display = str(work_item_id) if work_item_id else "untracked"
                    conflicts = lock_manager.acquire(project, paths, owner, wi_display)
                    if conflicts:
                        return {
                            "acquired": False,
                            "conflicts": [c.to_dict() for c in conflicts],
                        }
                    return {"acquired": True, "paths": paths, "owner": owner}

                if action == "release":
                    if not project:
                        return {"error": "project is required for release"}
                    paths = (metadata or {}).get("paths")
                    wi_display = str(work_item_id) if work_item_id else None
                    released = lock_manager.release(
                        project,
                        paths=paths if isinstance(paths, list) else None,
                        work_item_id=wi_display,
                        owner=assignee,
                    )
                    return {"released": released}

                if action == "check":
                    if not project:
                        return {"error": "project is required for check"}
                    paths = (metadata or {}).get("paths")
                    if not paths or not isinstance(paths, list):
                        return {"error": "metadata.paths (list of file paths) is required for check"}
                    conflicts = lock_manager.check(project, paths, owner=assignee)
                    return {
                        "clear": len(conflicts) == 0,
                        "conflicts": [c.to_dict() for c in conflicts],
                    }

                if action == "list":
                    if not project:
                        return {"error": "project is required for list"}
                    active_locks = lock_manager.list_locks(
                        project,
                        owner=assignee,
                        work_item_id=str(work_item_id) if work_item_id else None,
                    )
                    return {"locks": [lk.to_dict() for lk in active_locks]}

                return {"error": f"Unknown action: {action}"}

            return await in_thread(svc.db, _do_locks)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("locks failed")
            return {"error": f"Internal error: {e}"}
