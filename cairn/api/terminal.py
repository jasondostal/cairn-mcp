"""Terminal endpoints — host CRUD, config, WebSocket proxy."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Path, HTTPException, WebSocket, WebSocketDisconnect

from cairn.core.services import Services

logger = logging.getLogger(__name__)


def register_routes(router: APIRouter, svc: Services, *, app=None, **kw):
    terminal_mgr = svc.terminal_host_manager
    terminal_config = svc.config.terminal

    @router.get("/terminal/config")
    def api_terminal_config():
        return {
            "backend": terminal_config.backend,
            "max_sessions": terminal_config.max_sessions,
        }

    @router.get("/terminal/hosts")
    def api_terminal_hosts():
        if not terminal_mgr:
            raise HTTPException(status_code=503, detail="Terminal not configured")
        return terminal_mgr.list()

    @router.post("/terminal/hosts", status_code=201)
    def api_terminal_create_host(body: dict):
        if not terminal_mgr:
            raise HTTPException(status_code=503, detail="Terminal not configured")
        try:
            return terminal_mgr.create(
                name=body.get("name", ""),
                hostname=body.get("hostname", ""),
                port=body.get("port", 22),
                username=body.get("username"),
                credential=body.get("credential"),
                auth_method=body.get("auth_method", "password"),
                ttyd_url=body.get("ttyd_url"),
                description=body.get("description"),
                metadata=body.get("metadata"),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/terminal/hosts/{host_id}")
    def api_terminal_get_host(host_id: int = Path(...)):
        if not terminal_mgr:
            raise HTTPException(status_code=503, detail="Terminal not configured")
        host = terminal_mgr.get(host_id)
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")
        return host

    @router.patch("/terminal/hosts/{host_id}")
    def api_terminal_update_host(host_id: int = Path(...), body: dict | None = None):
        if not terminal_mgr:
            raise HTTPException(status_code=503, detail="Terminal not configured")
        return terminal_mgr.update(host_id, **(body or {}))

    @router.delete("/terminal/hosts/{host_id}")
    def api_terminal_delete_host(host_id: int = Path(...)):
        if not terminal_mgr:
            raise HTTPException(status_code=503, detail="Terminal not configured")
        return terminal_mgr.delete(host_id)

    # WebSocket proxy (native mode only) — registered on app, not router
    if terminal_config.backend == "native" and terminal_mgr and app:
        import asyncio

        @app.websocket("/terminal/ws/{host_id}")
        async def ws_terminal(websocket: WebSocket, host_id: int):
            await websocket.accept()

            host = terminal_mgr.get(host_id, decrypt=True)
            if not host:
                await websocket.close(code=4004, reason="Host not found")
                return

            credential = host.get("credential")
            if not credential:
                await websocket.close(code=4001, reason="No credentials available")
                return

            try:
                import asyncssh

                connect_kwargs = dict(
                    host=host["hostname"],
                    port=host["port"],
                    username=host["username"],
                    known_hosts=None,
                    connect_timeout=terminal_config.connect_timeout,
                )
                if host["auth_method"] == "key":
                    connect_kwargs["client_keys"] = [asyncssh.import_private_key(credential)]
                else:
                    connect_kwargs["password"] = credential

                async with asyncssh.connect(**connect_kwargs) as conn:
                    process = await conn.create_process(
                        term_type="xterm-256color",
                        term_size=(80, 24),
                    )

                    async def ws_to_ssh():
                        try:
                            while True:
                                data = await websocket.receive_text()
                                if data.startswith('{"type":"resize"'):
                                    try:
                                        msg = json.loads(data)
                                        if msg.get("type") == "resize":
                                            cols = msg.get("cols", 80)
                                            rows = msg.get("rows", 24)
                                            process.change_terminal_size(cols, rows)
                                            continue
                                    except (json.JSONDecodeError, TypeError):
                                        pass
                                process.stdin.write(data)
                        except WebSocketDisconnect:
                            pass

                    async def ssh_to_ws():
                        try:
                            async for data in process.stdout:
                                await websocket.send_text(data)
                        except Exception:
                            pass

                    await asyncio.gather(ws_to_ssh(), ssh_to_ws())

            except ImportError:
                await websocket.close(code=4500, reason="asyncssh not installed")
            except Exception as e:
                logger.error("Terminal WebSocket error for host %d: %s", host_id, e)
                try:
                    await websocket.send_text(f"\r\n\x1b[31mConnection error: {e}\x1b[0m\r\n")
                    await websocket.close(code=4500, reason=str(e)[:120])
                except Exception:
                    pass
