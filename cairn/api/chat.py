"""Chat endpoint — agentic LLM with tool calling + SSE streaming."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from cairn.core.services import Services

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 10


def register_routes(router: APIRouter, svc: Services, **kw):
    from cairn.chat_tools import CHAT_TOOLS, SYSTEM_PROMPT as CHAT_SYSTEM_PROMPT, ChatToolExecutor

    llm = svc.llm
    conv_mgr = svc.conversation_manager

    # ---- Synchronous endpoint (preserved for backwards compat) ----

    @router.post("/chat")
    def api_chat(body: dict):
        if llm is None:
            raise HTTPException(status_code=503, detail="LLM backend not configured")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=422, detail="messages array is required")

        max_tokens = min(body.get("max_tokens", 2048), 4096)

        if body.get("tools") is False or not llm.supports_tool_use():
            try:
                response = llm.generate(messages, max_tokens=max_tokens)
                return {"response": response, "model": llm.get_model_name()}
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"LLM error: {e}")

        executor = ChatToolExecutor(svc)

        conversation = list(messages)
        if not any(m.get("role") == "system" for m in conversation):
            conversation.insert(0, {"role": "system", "content": CHAT_SYSTEM_PROMPT})

        tool_call_log: list[dict] = []
        result = None

        try:
            for _iteration in range(MAX_AGENT_ITERATIONS):
                result = llm.generate_with_tools(conversation, CHAT_TOOLS, max_tokens)

                if result.stop_reason != "tool_use" or not result.tool_calls:
                    break

                tool_results = []
                for tc in result.tool_calls:
                    output = executor.execute(tc.name, tc.input)
                    try:
                        parsed_output = json.loads(output)
                    except (json.JSONDecodeError, TypeError):
                        parsed_output = output
                    tool_call_log.append({
                        "name": tc.name,
                        "input": tc.input,
                        "output": parsed_output,
                    })
                    tool_results.append({
                        "tool_use_id": tc.id,
                        "content": output,
                        "status": "success",
                    })

                assistant_msg: dict = {"role": "assistant"}
                if result.text:
                    assistant_msg["content"] = result.text
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in result.tool_calls
                ]
                conversation.append(assistant_msg)
                conversation.append({"role": "tool_result", "results": tool_results})

            response_text = (result.text if result else "") or ""
            return {
                "response": response_text,
                "model": llm.get_model_name(),
                "tool_calls": tool_call_log if tool_call_log else None,
            }
        except Exception as e:
            logger.error("Agentic chat error: %s", e, exc_info=True)
            raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    # ---- SSE streaming endpoint ----

    def _sse_event(event_type: str, data: dict) -> str:
        """Format a server-sent event."""
        return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"

    def _stream_chat(
        messages: list[dict], max_tokens: int,
        conversation_id: int | None = None,
        project: str | None = None,
    ) -> Iterator[str]:
        """Run the agentic loop, yielding SSE events.

        If conversation_id is set, persists the user message (last in the list)
        and the final assistant response to the conversation store.
        If project is set, adds project context to the system prompt.
        """
        model_name = llm.get_model_name()
        use_tools = llm.supports_tool_use()

        # Persist the user message if tracking a conversation
        if conversation_id:
            last_user = next(
                (m for m in reversed(messages) if m.get("role") == "user"), None,
            )
            if last_user:
                conv_mgr.add_message(
                    conversation_id, "user", content=last_user.get("content"),
                )

        # Accumulators for persistence
        all_text = ""
        all_tool_calls: list[dict] = []

        if not use_tools:
            for event in llm.generate_stream(messages, max_tokens):
                if event.type == "text_delta" and event.text:
                    all_text += event.text
                    yield _sse_event("text_delta", {"text": event.text})
            # Persist assistant response
            if conversation_id:
                conv_mgr.add_message(
                    conversation_id, "assistant",
                    content=all_text, model=model_name,
                )
                conv_mgr.auto_title(conversation_id)
            yield _sse_event("done", {"model": model_name})
            return

        executor = ChatToolExecutor(svc)
        conversation = list(messages)
        if not any(m.get("role") == "system" for m in conversation):
            system_content = CHAT_SYSTEM_PROMPT
            if project:
                system_content += f"\n\nProject context: The user is working in the '{project}' project. Default tool calls to this project when applicable."
            conversation.insert(0, {"role": "system", "content": system_content})

        for _iteration in range(MAX_AGENT_ITERATIONS):
            result = None
            turn_text = ""  # Accumulate text from deltas for this iteration
            for event in llm.generate_with_tools_stream(conversation, CHAT_TOOLS, max_tokens):
                if event.type == "text_delta" and event.text:
                    turn_text += event.text
                    yield _sse_event("text_delta", {"text": event.text})
                elif event.type == "response_complete":
                    result = event.response

            if result is None:
                break

            # Use result.text if available, fall back to streamed deltas
            effective_text = result.text or turn_text
            if effective_text:
                all_text = effective_text  # Last turn's text is the final response

            if result.stop_reason != "tool_use" or not result.tool_calls:
                break

            # Execute tool calls
            tool_results = []
            for tc in result.tool_calls:
                yield _sse_event("tool_call_start", {
                    "id": tc.id,
                    "name": tc.name,
                    "args": tc.input,
                })

                output = executor.execute(tc.name, tc.input)
                try:
                    parsed_output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    parsed_output = output

                yield _sse_event("tool_call_result", {
                    "id": tc.id,
                    "name": tc.name,
                    "output": parsed_output,
                })

                all_tool_calls.append({
                    "name": tc.name,
                    "input": tc.input,
                    "output": parsed_output,
                })

                tool_results.append({
                    "tool_use_id": tc.id,
                    "content": output,
                    "status": "success",
                })

            # Build conversation for next iteration
            assistant_msg: dict = {"role": "assistant"}
            if result.text:
                assistant_msg["content"] = result.text
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in result.tool_calls
            ]
            conversation.append(assistant_msg)
            conversation.append({"role": "tool_result", "results": tool_results})

        # Persist assistant response
        if conversation_id:
            conv_mgr.add_message(
                conversation_id, "assistant",
                content=all_text,
                tool_calls=all_tool_calls if all_tool_calls else None,
                model=model_name,
            )
            conv_mgr.auto_title(conversation_id)

        yield _sse_event("done", {"model": model_name})

    @router.post("/chat/stream")
    def api_chat_stream(body: dict):
        if llm is None:
            raise HTTPException(status_code=503, detail="LLM backend not configured")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=422, detail="messages array is required")

        max_tokens = min(body.get("max_tokens", 2048), 4096)
        conversation_id = body.get("conversation_id")
        project = body.get("project") or None

        def event_generator() -> Iterator[str]:
            try:
                yield from _stream_chat(messages, max_tokens, conversation_id, project)
            except Exception as e:
                logger.error("Streaming chat error: %s", e, exc_info=True)
                yield _sse_event("error", {"message": str(e)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
