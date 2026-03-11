"""Document attachment endpoints — upload, serve, list, delete."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path, UploadFile
from fastapi.responses import Response

from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, **_kw) -> None:
    project_manager = svc.project_manager

    @router.post("/docs/{doc_id}/attachments")
    async def api_upload_attachment(doc_id: int = Path(...), file: UploadFile = ...):
        """Upload an attachment to a document."""
        data = await file.read()
        mime_type = file.content_type or "application/octet-stream"
        filename = file.filename or "untitled"

        try:
            result = project_manager.upload_attachment(doc_id, filename, mime_type, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return result

    @router.get("/docs/{doc_id}/attachments")
    def api_list_attachments(doc_id: int = Path(...)):
        """List all attachments for a document."""
        return project_manager.list_attachments(doc_id)

    @router.get("/attachments/{attachment_id}/{filename}")
    def api_serve_attachment(attachment_id: int = Path(...), filename: str = Path(...)):
        """Serve an attachment's binary content."""
        att = project_manager.get_attachment(attachment_id)
        if att is None:
            raise HTTPException(status_code=404, detail="Attachment not found")

        return Response(
            content=att["data"],
            media_type=att["mime_type"],
            headers={
                "Content-Disposition": f'inline; filename="{att["filename"]}"',
                "Cache-Control": "public, max-age=86400, immutable",
            },
        )

    @router.delete("/attachments/{attachment_id}")
    def api_delete_attachment(attachment_id: int = Path(...)):
        """Delete an attachment."""
        return project_manager.delete_attachment(attachment_id)
