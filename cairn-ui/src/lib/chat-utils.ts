/**
 * Shared utilities for chat UI — used by both /chat page and chat drawer.
 */

import type { ThreadMessageLike } from "@assistant-ui/react";
import type { ChatMessage } from "@/lib/api";

/** Convert stored ChatMessages to assistant-ui ThreadMessageLike format. */
export function toThreadMessages(messages: ChatMessage[]): ThreadMessageLike[] {
  return messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => {
      if (m.role === "user") {
        return {
          role: "user" as const,
          content: [{ type: "text" as const, text: m.content || "" }],
        };
      }
      // Assistant message — include tool calls + text
      const content: ThreadMessageLike["content"] = [];
      if (m.tool_calls) {
        for (const tc of m.tool_calls) {
          (content as Array<unknown>).push({
            type: "tool-call",
            toolCallId: `${tc.name}-restored-${m.id}`,
            toolName: tc.name,
            args: tc.input,
            result: tc.output,
            argsText: JSON.stringify(tc.input),
          });
        }
      }
      if (m.content) {
        (content as Array<unknown>).push({
          type: "text",
          text: m.content,
        });
      }
      return {
        role: "assistant" as const,
        content,
      };
    });
}
