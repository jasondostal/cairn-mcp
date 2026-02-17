"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  useLocalRuntime,
  AssistantRuntimeProvider,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import {
  cairnChatAdapter,
  setConversationId,
  setProjectScope,
} from "@/lib/chat-adapter";
import { api, type Conversation, type ChatMessage, type Project } from "@/lib/api";
import { ChatThread } from "@/components/chat/thread";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { Button } from "@/components/ui/button";
import { RotateCcw, PanelLeftClose, PanelLeft } from "lucide-react";

/** Convert stored ChatMessages to assistant-ui ThreadMessageLike format. */
function toThreadMessages(messages: ChatMessage[]): ThreadMessageLike[] {
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

export default function ChatPage() {
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [initialMessages, setInitialMessages] = useState<
    ThreadMessageLike[] | undefined
  >(undefined);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<string>("");

  // Load project list for the scope selector
  useEffect(() => {
    api.projects({ limit: "100" }).then((r) => setProjects(r.items)).catch(() => {});
  }, []);

  // Sync project scope to the adapter
  useEffect(() => {
    setProjectScope(activeProject || null);
  }, [activeProject]);

  // Create runtime with initial messages for the loaded conversation
  const runtime = useLocalRuntime(cairnChatAdapter, {
    initialMessages,
  });

  const runtimeRef = useRef(runtime);
  runtimeRef.current = runtime;

  // Create a new conversation on the backend, set it active
  const createNewConversation = useCallback(async () => {
    try {
      const conv = await api.createConversation({});
      setActiveConvId(conv.id);
      setConversationId(conv.id);
      return conv;
    } catch {
      return null;
    }
  }, []);

  const handleNewChat = useCallback(() => {
    setActiveConvId(null);
    setConversationId(null);
    setInitialMessages(undefined);
    runtimeRef.current.switchToNewThread();
  }, []);

  const handleSelectConversation = useCallback(
    async (conv: Conversation) => {
      try {
        const result = await api.conversationMessages(conv.id);
        const msgs = toThreadMessages(result.messages);
        setActiveConvId(conv.id);
        setConversationId(conv.id);
        setInitialMessages(msgs);
        // Force new thread with these messages
        runtimeRef.current.switchToNewThread();
      } catch {
        // silent
      }
    },
    [],
  );

  // Auto-create conversation on first message if none active
  useEffect(() => {
    if (!activeConvId) {
      setConversationId(null);
    }
  }, [activeConvId]);

  // Keyboard shortcut: N for new conversation (when not in an input)
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const target = e.target as HTMLElement;
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
        e.preventDefault();
        handleNewChat();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [handleNewChat]);

  // When user sends first message without a conversation, create one
  const ensureConversation = useCallback(async () => {
    if (!activeConvId) {
      const conv = await createNewConversation();
      if (conv) {
        setActiveConvId(conv.id);
        setConversationId(conv.id);
      }
    }
  }, [activeConvId, createNewConversation]);

  return (
    <div className="flex h-full -m-4 md:-m-6">
      {/* Conversation sidebar */}
      {sidebarOpen && (
        <div className="w-56 shrink-0 hidden md:block">
          <ConversationSidebar
            activeId={activeConvId}
            onSelect={handleSelectConversation}
            onNew={handleNewChat}
          />
        </div>
      )}

      {/* Main chat area */}
      <div className="flex flex-1 flex-col min-w-0">
        <AssistantRuntimeProvider runtime={runtime}>
          {/* Header */}
          <div className="shrink-0 border-b px-4 py-3 md:px-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 hidden md:flex"
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
                >
                  {sidebarOpen ? (
                    <PanelLeftClose className="h-4 w-4" />
                  ) : (
                    <PanelLeft className="h-4 w-4" />
                  )}
                </Button>
                <h1 className="text-lg font-semibold">Chat</h1>
                {/* Project scope selector */}
                <select
                  value={activeProject}
                  onChange={(e) => setActiveProject(e.target.value)}
                  className="h-7 rounded-md border bg-background px-2 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">All projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleNewChat}
                  className="h-7 px-2 text-xs"
                  title="New conversation (N)"
                >
                  <RotateCcw className="mr-1 h-3 w-3" />
                  New
                </Button>
              </div>
            </div>
          </div>

          {/* Thread */}
          <div className="flex-1 min-h-0">
            <ChatThread onFirstMessage={ensureConversation} />
          </div>
        </AssistantRuntimeProvider>
      </div>
    </div>
  );
}
