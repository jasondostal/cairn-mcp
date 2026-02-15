"""Chat endpoint — agentic LLM with tool calling."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from cairn.core.services import Services

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 10


def register_routes(router: APIRouter, svc: Services, **kw):
    from cairn.chat_tools import CHAT_TOOLS, SYSTEM_PROMPT as CHAT_SYSTEM_PROMPT, ChatToolExecutor

    llm = svc.llm

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
