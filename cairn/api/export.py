"""Export and drift detection endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import Response

from cairn.core.services import Services


def register_routes(router: APIRouter, svc: Services, **kw):
    memory_store = svc.memory_store

    @router.get("/export")
    def api_export(
        project: str = Query(..., description="Project name (required)"),
        format: str = Query("json", description="Export format: json or markdown"),
    ):
        memories = memory_store.export_project(project)

        if format == "markdown":
            lines = [f"# {project} — Memory Export\n"]
            lines.append(f"Exported: {datetime.now(timezone.utc).isoformat()}")
            lines.append(f"Total memories: {len(memories)}\n")

            for m in memories:
                lines.append(f"---\n")
                lines.append(f"## Memory #{m['id']} — {m['memory_type']}")
                lines.append(f"**Importance:** {m['importance']}")
                lines.append(f"**Created:** {m['created_at']}")
                if m["summary"]:
                    lines.append(f"**Summary:** {m['summary']}")
                if m["tags"]:
                    lines.append(f"**Tags:** {', '.join(m['tags'])}")
                if m["related_files"]:
                    lines.append(f"**Files:** {', '.join(m['related_files'])}")
                lines.append(f"\n{m['content']}\n")

            content = "\n".join(lines)
            return Response(
                content=content,
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{project}-export.md"'},
            )

        return {
            "project": project,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memory_count": len(memories),
            "memories": memories,
        }

    @router.get("/drift")
    def api_drift(
        project: str | None = Query(None),
    ):
        return svc.drift_detector.check(project=project, files=None)

    @router.post("/drift")
    def api_drift_post(body: dict):
        project = body.get("project")
        files = body.get("files")
        return svc.drift_detector.check(project=project, files=files)
