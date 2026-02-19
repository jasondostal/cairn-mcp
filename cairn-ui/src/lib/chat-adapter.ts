/**
 * ChatModelAdapter for assistant-ui — bridges cairn's /api/chat/stream SSE
 * endpoint to the assistant-ui LocalRuntime via an async generator.
 *
 * SSE event types from the backend:
 *   - text_delta: { text } — incremental token
 *   - tool_call_start: { id, name, args } — tool invocation beginning
 *   - tool_call_result: { id, name, output } — tool execution complete
 *   - done: { model } — stream finished
 *   - error: { message } — server error
 */

import type {
  ChatModelAdapter,
  ChatModelRunOptions,
  ChatModelRunResult,
  ThreadMessage,
} from "@assistant-ui/react";

const BASE = "/api";

/** Extract plain text from a ThreadMessage's content parts. */
function extractText(msg: ThreadMessage): string {
  return msg.content
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
}

/** Convert assistant-ui ThreadMessage[] to the simple {role, content}[] our backend expects. */
function toApiMessages(
  messages: readonly ThreadMessage[],
): Array<{ role: string; content: string }> {
  return messages.map((msg) => ({
    role: msg.role,
    content: extractText(msg),
  }));
}

interface ToolCallAccumulator {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  result?: unknown;
  argsText: string;
}

/** Build a ChatModelRunResult from the accumulated state. */
function buildResult(
  text: string,
  toolCalls: Map<string, ToolCallAccumulator>,
  model: string,
): ChatModelRunResult {
  const content: Array<unknown> = [];

  // Tool calls first
  for (const tc of toolCalls.values()) {
    content.push({
      type: "tool-call" as const,
      toolCallId: tc.toolCallId,
      toolName: tc.toolName,
      args: tc.args,
      result: tc.result,
      argsText: tc.argsText,
    });
  }

  // Text
  if (text) {
    content.push({
      type: "text" as const,
      text,
    });
  }

  return {
    content: content as ChatModelRunResult["content"],
    metadata: {
      custom: { model },
    },
  };
}

// ---------------------------------------------------------------------------
// Shared SSE streaming logic — used by both module-level adapter and factory
// ---------------------------------------------------------------------------

interface AdapterState {
  getConversationId: () => number | null;
  setConversationId: (id: number | null) => void;
  getProjectScope: () => string | null;
  onConversationCreated: () => ((id: number) => void) | null;
  onStreamComplete: () => (() => void) | null;
}

async function* runStream(
  { messages, abortSignal }: ChatModelRunOptions,
  state: AdapterState,
): AsyncGenerator<ChatModelRunResult> {
  // Auto-create conversation if none active
  if (state.getConversationId() === null) {
    try {
      const convRes = await fetch(`${BASE}/chat/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: state.getProjectScope() || undefined }),
      });
      if (convRes.ok) {
        const conv = await convRes.json();
        state.setConversationId(conv.id);
        state.onConversationCreated()?.(conv.id);
      }
    } catch {
      // Continue without conversation tracking
    }
  }

  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: toApiMessages(messages),
      max_tokens: 2048,
      conversation_id: state.getConversationId(),
      project: state.getProjectScope(),
    }),
    signal: abortSignal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }

  if (!res.body) {
    throw new Error("No response body for streaming");
  }

  // Parse the SSE stream
  let textAccumulator = "";
  const toolCalls = new Map<string, ToolCallAccumulator>();
  let model = "";

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE events (separated by double newlines)
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const eventBlock of events) {
        if (!eventBlock.trim()) continue;

        let eventType = "";
        let eventData = "";

        for (const line of eventBlock.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7);
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6);
          }
        }

        if (!eventType || !eventData) continue;

        let parsed: Record<string, unknown>;
        try {
          parsed = JSON.parse(eventData);
        } catch {
          continue;
        }

        switch (eventType) {
          case "text_delta": {
            textAccumulator += (parsed.text as string) ?? "";
            yield buildResult(textAccumulator, toolCalls, model);
            break;
          }
          case "tool_call_start": {
            const id = parsed.id as string;
            toolCalls.set(id, {
              toolCallId: id,
              toolName: parsed.name as string,
              args: (parsed.args as Record<string, unknown>) ?? {},
              argsText: JSON.stringify(parsed.args ?? {}),
            });
            yield buildResult(textAccumulator, toolCalls, model);
            break;
          }
          case "tool_call_result": {
            const tcId = parsed.id as string;
            const existing = toolCalls.get(tcId);
            if (existing) {
              existing.result = parsed.output;
            }
            yield buildResult(textAccumulator, toolCalls, model);
            break;
          }
          case "done": {
            model = (parsed.model as string) ?? "";
            break;
          }
          case "error": {
            throw new Error(
              (parsed.message as string) ?? "Streaming error",
            );
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  // Final yield with complete state
  yield buildResult(textAccumulator, toolCalls, model);

  // Notify consumer that streaming is done
  state.onStreamComplete()?.();
}

// ---------------------------------------------------------------------------
// Module-level adapter (used by /chat page — backward compatible)
// ---------------------------------------------------------------------------

let _conversationId: number | null = null;
let _projectScope: string | null = null;
let _onConversationCreated: ((id: number) => void) | null = null;
let _onStreamComplete: (() => void) | null = null;

export function setConversationId(id: number | null) {
  _conversationId = id;
}

export function getConversationId(): number | null {
  return _conversationId;
}

export function setProjectScope(project: string | null) {
  _projectScope = project;
}

export function setOnConversationCreated(cb: ((id: number) => void) | null) {
  _onConversationCreated = cb;
}

export function setOnStreamComplete(cb: (() => void) | null) {
  _onStreamComplete = cb;
}

const _moduleState: AdapterState = {
  getConversationId: () => _conversationId,
  setConversationId: (id) => { _conversationId = id; },
  getProjectScope: () => _projectScope,
  onConversationCreated: () => _onConversationCreated,
  onStreamComplete: () => _onStreamComplete,
};

export const cairnChatAdapter: ChatModelAdapter = {
  async *run(options: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult> {
    yield* runStream(options, _moduleState);
  },
};

// ---------------------------------------------------------------------------
// Factory — creates isolated adapter instances (used by chat drawer)
// ---------------------------------------------------------------------------

export interface ChatAdapterInstance {
  adapter: ChatModelAdapter;
  setConversationId: (id: number | null) => void;
  getConversationId: () => number | null;
  setProjectScope: (project: string | null) => void;
  setOnConversationCreated: (cb: ((id: number) => void) | null) => void;
  setOnStreamComplete: (cb: (() => void) | null) => void;
}

export function createChatAdapter(): ChatAdapterInstance {
  let conversationId: number | null = null;
  let projectScope: string | null = null;
  let onConversationCreated: ((id: number) => void) | null = null;
  let onStreamComplete: (() => void) | null = null;

  const state: AdapterState = {
    getConversationId: () => conversationId,
    setConversationId: (id) => { conversationId = id; },
    getProjectScope: () => projectScope,
    onConversationCreated: () => onConversationCreated,
    onStreamComplete: () => onStreamComplete,
  };

  const adapter: ChatModelAdapter = {
    async *run(options: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult> {
      yield* runStream(options, state);
    },
  };

  return {
    adapter,
    setConversationId: (id) => { conversationId = id; },
    getConversationId: () => conversationId,
    setProjectScope: (project) => { projectScope = project; },
    setOnConversationCreated: (cb) => { onConversationCreated = cb; },
    setOnStreamComplete: (cb) => { onStreamComplete = cb; },
  };
}
