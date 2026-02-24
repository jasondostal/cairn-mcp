"""Tests for OpenAI-compatible LLM tool calling support."""

import json
import http.server
import threading
from unittest.mock import patch

import pytest

from cairn.config import LLMConfig
from cairn.llm.openai_compat import OpenAICompatibleLLM
from cairn.llm.interface import LLMResponse, ToolCallInfo, StreamEvent


# ── Helpers ──────────────────────────────────────────────────

def _make_config(base_url: str) -> LLMConfig:
    """Build a minimal LLMConfig pointing at a local mock server."""
    return LLMConfig(
        openai_model="test-model",
        openai_api_key="test-key",
        openai_base_url=base_url,
    )


class _MockHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that returns canned OpenAI-format responses."""

    # Class-level response override — set before each test
    response_body: dict | None = None
    stream_lines: list[str] | None = None
    last_request_body: dict | None = None
    status_code: int = 200

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        _MockHandler.last_request_body = body

        self.send_response(_MockHandler.status_code)
        self.send_header("Content-Type", "application/json")

        if _MockHandler.stream_lines is not None:
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for line in _MockHandler.stream_lines:
                self.wfile.write((line + "\n").encode())
        else:
            self.end_headers()
            self.wfile.write(json.dumps(_MockHandler.response_body).encode())

    def log_message(self, *args):
        pass  # Suppress request logs during tests


@pytest.fixture()
def mock_server():
    """Start a local HTTP server for testing, yield the base URL."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def llm(mock_server):
    """Create an OpenAICompatibleLLM pointing at the mock server."""
    return OpenAICompatibleLLM(_make_config(mock_server))


# ── Tests ────────────────────────────────────────────────────


def test_supports_tool_use(llm):
    """Fresh instance should report tool support."""
    assert llm.supports_tool_use() is True


def test_supports_tool_use_disabled(llm):
    """After marking unsupported, should return False."""
    llm._tools_unsupported = True
    assert llm.supports_tool_use() is False


SAMPLE_TOOLS = [
    {
        "name": "search_memories",
        "description": "Search memories",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


class TestGenerateWithTools:
    """Non-streaming tool calling."""

    def test_text_only_response(self, llm):
        """Model returns text without calling tools."""
        _MockHandler.response_body = {
            "choices": [{
                "message": {"content": "Hello!", "tool_calls": None},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        result = llm.generate_with_tools(
            [{"role": "user", "content": "hi"}], SAMPLE_TOOLS,
        )
        assert isinstance(result, LLMResponse)
        assert result.text == "Hello!"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"

    def test_tool_call_response(self, llm):
        """Model returns a tool call."""
        _MockHandler.response_body = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "search_memories",
                            "arguments": '{"query": "recent decisions"}',
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15},
        }
        result = llm.generate_with_tools(
            [{"role": "user", "content": "search for recent decisions"}],
            SAMPLE_TOOLS,
        )
        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.id == "call_abc123"
        assert tc.name == "search_memories"
        assert tc.input == {"query": "recent decisions"}

    def test_multiple_tool_calls(self, llm):
        """Model returns multiple tool calls in one response."""
        _MockHandler.response_body = {
            "choices": [{
                "message": {
                    "content": "Let me look that up.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search_memories",
                                "arguments": '{"query": "foo"}',
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "search_memories",
                                "arguments": '{"query": "bar"}',
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
        }
        result = llm.generate_with_tools(
            [{"role": "user", "content": "search foo and bar"}], SAMPLE_TOOLS,
        )
        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 2
        assert result.text == "Let me look that up."

    def test_tools_sent_in_request(self, llm):
        """Verify tools are included in the request payload."""
        _MockHandler.response_body = {
            "choices": [{
                "message": {"content": "OK"},
                "finish_reason": "stop",
            }],
            "usage": {},
        }
        llm.generate_with_tools(
            [{"role": "user", "content": "test"}], SAMPLE_TOOLS,
        )
        body = _MockHandler.last_request_body
        assert "tools" in body
        assert body["tools"][0]["type"] == "function"
        assert body["tools"][0]["function"]["name"] == "search_memories"

    def test_graceful_degradation(self, llm):
        """If API rejects tools with 400, falls back to plain generate."""
        _MockHandler.status_code = 400
        _MockHandler.response_body = {"error": {"message": "tool calling not supported"}}

        # The 400 will trigger graceful degradation. We need to handle that
        # the fallback generate() call also hits the mock. Reset status for that.
        original_generate = llm.generate

        def mock_generate(messages, max_tokens=1024):
            _MockHandler.status_code = 200
            _MockHandler.response_body = {
                "choices": [{
                    "message": {"content": "fallback response"},
                    "finish_reason": "stop",
                }],
                "usage": {},
            }
            return original_generate(messages, max_tokens)

        with patch.object(llm, "generate", side_effect=mock_generate):
            result = llm.generate_with_tools(
                [{"role": "user", "content": "test"}], SAMPLE_TOOLS,
            )
        assert result.text == "fallback response"
        assert result.stop_reason == "end_turn"
        assert llm._tools_unsupported is True

    def test_tools_unsupported_skips(self, llm):
        """When _tools_unsupported is set, goes straight to generate()."""
        llm._tools_unsupported = True
        _MockHandler.response_body = {
            "choices": [{
                "message": {"content": "plain text"},
                "finish_reason": "stop",
            }],
            "usage": {},
        }
        _MockHandler.status_code = 200
        result = llm.generate_with_tools(
            [{"role": "user", "content": "test"}], SAMPLE_TOOLS,
        )
        assert result.text == "plain text"
        # Should NOT have sent tools in the request
        body = _MockHandler.last_request_body
        assert "tools" not in body


class TestPrepareToolMessages:
    """Message format conversion for the OpenAI API."""

    def test_plain_messages(self, llm):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = llm._prepare_tool_messages(messages)
        assert len(result) == 3
        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi there!"}

    def test_assistant_with_tool_calls(self, llm):
        messages = [
            {
                "role": "assistant",
                "content": "Let me search.",
                "tool_calls": [
                    {"id": "call_1", "name": "search", "input": {"q": "test"}},
                ],
            },
        ]
        result = llm._prepare_tool_messages(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Let me search."
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "search"
        assert json.loads(tc["function"]["arguments"]) == {"q": "test"}

    def test_tool_result_messages(self, llm):
        messages = [
            {
                "role": "tool_result",
                "results": [
                    {"tool_use_id": "call_1", "content": '{"found": true}', "status": "success"},
                    {"tool_use_id": "call_2", "content": "OK", "status": "success"},
                ],
            },
        ]
        result = llm._prepare_tool_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == '{"found": true}'
        assert result[1]["role"] == "tool"
        assert result[1]["tool_call_id"] == "call_2"


class TestGenerateWithToolsStream:
    """Streaming tool calling."""

    def test_text_only_stream(self, llm):
        """Streaming response with text only, no tools."""
        _MockHandler.status_code = 200
        _MockHandler.response_body = None
        _MockHandler.stream_lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        events = list(llm.generate_with_tools_stream(
            [{"role": "user", "content": "hi"}], SAMPLE_TOOLS,
        ))
        text_events = [e for e in events if e.type == "text_delta"]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello"
        assert text_events[1].text == " world"

        complete = [e for e in events if e.type == "response_complete"]
        assert len(complete) == 1
        resp = complete[0].response
        assert resp.text == "Hello world"
        assert resp.stop_reason == "end_turn"
        assert resp.tool_calls == []

    def test_tool_call_stream(self, llm):
        """Streaming response with tool calls."""
        _MockHandler.status_code = 200
        _MockHandler.response_body = None
        _MockHandler.stream_lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_x","function":{"name":"search_memories","arguments":""}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"query\\""}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"test\\"}"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ]
        events = list(llm.generate_with_tools_stream(
            [{"role": "user", "content": "search"}], SAMPLE_TOOLS,
        ))
        complete = [e for e in events if e.type == "response_complete"]
        assert len(complete) == 1
        resp = complete[0].response
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_calls) == 1
        tc = resp.tool_calls[0]
        assert tc.id == "call_x"
        assert tc.name == "search_memories"
        assert tc.input == {"query": "test"}

    def test_tools_unsupported_fallback_stream(self, llm):
        """When tools unsupported, falls back to plain streaming."""
        llm._tools_unsupported = True
        _MockHandler.status_code = 200
        _MockHandler.response_body = None
        _MockHandler.stream_lines = [
            'data: {"choices":[{"delta":{"content":"plain"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        events = list(llm.generate_with_tools_stream(
            [{"role": "user", "content": "hi"}], SAMPLE_TOOLS,
        ))
        text_events = [e for e in events if e.type == "text_delta"]
        assert text_events[0].text == "plain"
