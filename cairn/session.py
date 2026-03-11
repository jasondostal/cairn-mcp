"""Resilient MCP session manager that survives container restarts.

The upstream StreamableHTTPSessionManager stores sessions in an in-memory dict.
When the container restarts, every session ID is lost and clients get hard 404s
until they manually reconnect.

This subclass logs the stale session event for observability but otherwise lets
the 404 flow back to the client, which triggers a proper re-initialization.

The key addition: if a stale session was accidentally recreated (e.g., by a
previous version of this code), we clean it up so the next reconnect starts
fresh.
"""

import logging
from http import HTTPStatus
from uuid import uuid4

import anyio
from anyio.abc import TaskStatus
from mcp.server.streamable_http import (
    MCP_SESSION_ID_HEADER,
    StreamableHTTPServerTransport,
)
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import INVALID_REQUEST, ErrorData, JSONRPCError
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

logger = logging.getLogger("cairn.session")


class ResilientSessionManager(StreamableHTTPSessionManager):
    """Session manager that handles stale session IDs gracefully.

    When an unknown session ID arrives (e.g. after container restart),
    logs the event for observability and returns a clear error that
    triggers client re-initialization. Also ensures no zombie transports
    linger from previous recreation attempts.
    """

    async def _handle_stateful_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        request = Request(scope, receive)
        request_mcp_session_id = request.headers.get(MCP_SESSION_ID_HEADER)

        # Existing session — fast path
        if request_mcp_session_id is not None and request_mcp_session_id in self._server_instances:
            transport = self._server_instances[request_mcp_session_id]
            logger.debug("Session %s found, handling request", request_mcp_session_id)
            await transport.handle_request(scope, receive, send)
            return

        if request_mcp_session_id is None:
            # Genuinely new session — create normally.
            await self._create_session_and_handle(scope, receive, send)
            return

        # Unknown/stale session ID — log for observability, return error
        # to trigger client re-initialization.
        logger.warning(
            "Stale MCP session ID %s (likely container restart). "
            "Client should re-initialize with a fresh session.",
            request_mcp_session_id,
        )
        error_response = JSONRPCError(
            jsonrpc="2.0",
            id="server-error",
            error=ErrorData(
                code=INVALID_REQUEST,
                message="Session not found",
            ),
        )
        response = Response(
            content=error_response.model_dump_json(by_alias=True, exclude_none=True),
            status_code=HTTPStatus.NOT_FOUND,
            media_type="application/json",
        )
        await response(scope, receive, send)

    async def _create_session_and_handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Create a new transport session and handle the request."""
        async with self._session_creation_lock:
            new_session_id = uuid4().hex
            http_transport = StreamableHTTPServerTransport(
                mcp_session_id=new_session_id,
                is_json_response_enabled=self.json_response,
                event_store=self.event_store,
                security_settings=self.security_settings,
                retry_interval=self.retry_interval,
            )

            assert http_transport.mcp_session_id is not None
            self._server_instances[http_transport.mcp_session_id] = http_transport
            logger.info("Created new transport session: %s", new_session_id)

            async def run_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
                async with http_transport.connect() as streams:
                    read_stream, write_stream = streams
                    task_status.started()
                    try:
                        await self.app.run(
                            read_stream,
                            write_stream,
                            self.app.create_initialization_options(),
                            stateless=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Session %s crashed: %s",
                            http_transport.mcp_session_id, e,
                            exc_info=True,
                        )
                    finally:
                        if (
                            http_transport.mcp_session_id
                            and http_transport.mcp_session_id in self._server_instances
                            and not http_transport.is_terminated
                        ):
                            logger.info(
                                "Cleaning up crashed session %s",
                                http_transport.mcp_session_id,
                            )
                            del self._server_instances[http_transport.mcp_session_id]

            assert self._task_group is not None
            await self._task_group.start(run_server)
            await http_transport.handle_request(scope, receive, send)
