"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Send, Bot, User, Loader2, Wrench, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToolCallEntry {
  name: string;
  input: Record<string, unknown>;
  output: unknown;
}

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  toolCalls?: ToolCallEntry[];
}

const STORAGE_KEY = "cairnChat";
const MAX_PERSISTED = 100;

function loadMessages(): Message[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(-MAX_PERSISTED) : [];
  } catch {
    return [];
  }
}

function toolDisplayName(name: string): string {
  return name.replace(/_/g, " ");
}

function toolInputSummary(name: string, input: Record<string, unknown>): string {
  if (name === "search_memories" && input.query) return `"${input.query}"`;
  if (name === "recall_memory" && input.ids) return `#${(input.ids as number[]).join(", #")}`;
  if (name === "store_memory" && input.project) return `in ${input.project}`;
  if (name === "list_tasks" && input.project) return `${input.project}`;
  if (name === "get_rules" && input.project) return `${input.project}`;
  return "";
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Persist messages to sessionStorage
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
    } catch {
      // quota exceeded — ignore
    }
  }, [messages]);

  // Scroll to bottom after paint
  useEffect(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setModel(null);
    sessionStorage.removeItem(STORAGE_KEY);
    inputRef.current?.focus();
  }, []);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || loading) return;

    const userMessage: Message = { role: "user", content };
    const updated = [...messages, userMessage];
    setMessages(updated);
    setInput("");
    setLoading(true);

    try {
      const result = await api.chat(updated, 2048);
      setModel(result.model);
      setMessages([
        ...updated,
        {
          role: "assistant",
          content: result.response,
          toolCalls: result.tool_calls ?? undefined,
        },
      ]);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Failed to get response";
      setMessages([
        ...updated,
        { role: "assistant", content: `Error: ${errorMsg}` },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="flex flex-col -m-4 md:-m-6"
      style={{ height: "calc(100vh - var(--removed, 0px))" }}
    >
      {/* Header */}
      <div className="shrink-0 border-b px-4 py-3 md:px-6">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Chat</h1>
          <div className="flex items-center gap-2">
            {model && (
              <span className="text-xs text-muted-foreground font-mono">
                {model}
              </span>
            )}
            {messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={handleNewChat} className="h-7 px-2 text-xs">
                <RotateCcw className="mr-1 h-3 w-3" />
                New
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 md:px-6">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Bot className="mx-auto mb-3 h-10 w-10 opacity-30" />
              <p className="text-sm">Talk to your Cairn LLM.</p>
              <p className="text-xs mt-1 opacity-60">
                The assistant can search and browse your memories.
              </p>
            </div>
          </div>
        )}

        <div className="mx-auto max-w-2xl space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-3",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {msg.role === "assistant" && (
                <div className="mt-1 shrink-0">
                  <Bot className="h-5 w-5 text-muted-foreground" />
                </div>
              )}
              <div
                className={cn(
                  "rounded-lg px-3 py-2 text-sm max-w-[80%]",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                {/* Tool calls */}
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="space-y-1 mb-2 pb-2 border-b border-border/50">
                    {msg.toolCalls.map((tc, j) => (
                      <details key={j} className="group">
                        <summary className="cursor-pointer text-xs text-muted-foreground flex items-center gap-1.5 hover:text-foreground transition-colors">
                          <Wrench className="h-3 w-3 shrink-0" />
                          <span className="font-medium">{toolDisplayName(tc.name)}</span>
                          {toolInputSummary(tc.name, tc.input) && (
                            <span className="opacity-60">{toolInputSummary(tc.name, tc.input)}</span>
                          )}
                        </summary>
                        <pre className="mt-1 text-[10px] bg-background/50 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all text-muted-foreground">
                          {JSON.stringify(tc.output, null, 2)}
                        </pre>
                      </details>
                    ))}
                  </div>
                )}
                {/* Message text */}
                <div className="whitespace-pre-wrap">{msg.content}</div>
              </div>
              {msg.role === "user" && (
                <div className="mt-1 shrink-0">
                  <User className="h-5 w-5 text-muted-foreground" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="mt-1 shrink-0">
                <Bot className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="bg-muted rounded-lg px-3 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t px-4 py-3 md:px-6">
        <div className="mx-auto max-w-2xl flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className={cn(
              "flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm",
              "ring-offset-background placeholder:text-muted-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
            disabled={loading}
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={loading || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
