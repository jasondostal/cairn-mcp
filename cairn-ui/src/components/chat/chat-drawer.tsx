"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  useLocalRuntime,
  AssistantRuntimeProvider,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { createChatAdapter, type ChatAdapterInstance } from "@/lib/chat-adapter";
import { toThreadMessages } from "@/lib/chat-utils";
import { api, type Project } from "@/lib/api";
import { ChatThread } from "@/components/chat/thread";
import { Button } from "@/components/ui/button";
import { SingleSelect } from "@/components/ui/single-select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { RotateCcw, MessageCircle, Bot, User, Wrench, SendHorizonal } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  demo?: boolean;
}

/* ---------- Demo static chat ---------- */

function DemoChat() {
  return (
    <Sheet open onOpenChange={() => {}}>
      <SheetContent
        side="left"
        className="flex flex-col gap-0 p-0 sm:max-w-xl w-full"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Chat</SheetTitle>
          <SheetDescription>Chat with your Cairn assistant</SheetDescription>
        </SheetHeader>

        {/* Header */}
        <div className="shrink-0 border-b px-4 py-3 pr-12">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageCircle className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold">Chat</span>
              <div className="inline-flex h-7 items-center rounded-md border border-input bg-background px-2 text-xs">
                cairn
              </div>
            </div>
            <Button variant="ghost" size="sm" className="h-7 px-2 text-xs">
              <RotateCcw className="mr-1 h-3 w-3" />
              New
            </Button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 md:px-6">
          <div className="mx-auto max-w-2xl space-y-4">
            {/* User 1 */}
            <div className="flex gap-3 justify-end">
              <div className="rounded-lg px-3 py-2 text-sm max-w-[80%] bg-primary text-primary-foreground">
                <div className="whitespace-pre-wrap">I&apos;ve been thinking about how agents navigate our codebase. Every session starts with a ton of grep and glob calls just to orient. What if we had semantic code indexing built into Cairn?</div>
              </div>
              <div className="mt-1 shrink-0">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
            </div>

            {/* Assistant 1 — with tool call */}
            <div className="flex gap-3 justify-start">
              <div className="mt-1 shrink-0">
                <Bot className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="max-w-[80%]">
                <div className="rounded-lg px-3 py-2 text-sm bg-muted">
                  <div className="my-1 rounded-md border border-border/50 bg-background/30 px-3 py-2 text-xs">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Wrench className="h-3 w-3 shrink-0" />
                      <span className="font-medium text-foreground/80">search memories</span>
                      <span className="opacity-60">&quot;embedding pipeline architecture&quot;</span>
                    </div>
                    <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[10px] text-muted-foreground">Found 3 results: #142 Embedding pipeline supports voyage-3-code + local fallback, #98 MemoryManager handles vector storage and retrieval, #167 Knowledge graph projects entities from memories</pre>
                  </div>
                  <div className="prose prose-sm prose-invert max-w-none break-words prose-p:leading-relaxed">
                    <p>That&apos;s a great direction. Right now agents burn significant context window on orientation — searching, reading, re-reading files they&apos;ve seen before. A semantic code index would let them jump straight to relevant code with a single query.</p>
                    <p>I searched our existing architecture to see what we can build on.</p>
                  </div>
                </div>
                <div className="mt-0.5 px-1 text-[10px] text-muted-foreground/60 font-mono">claude-opus-4-6</div>
              </div>
            </div>

            {/* User 2 */}
            <div className="flex gap-3 justify-end">
              <div className="rounded-lg px-3 py-2 text-sm max-w-[80%] bg-primary text-primary-foreground">
                <div className="whitespace-pre-wrap">Nice — so we already have the embedding infra. What would the approach look like end to end?</div>
              </div>
              <div className="mt-1 shrink-0">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
            </div>

            {/* Assistant 2 — the meaty response */}
            <div className="flex gap-3 justify-start">
              <div className="mt-1 shrink-0">
                <Bot className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="max-w-[80%]">
                <div className="rounded-lg px-3 py-2 text-sm bg-muted">
                  <div className="prose prose-sm prose-invert max-w-none break-words prose-p:leading-relaxed">
                    <p>Here&apos;s what I&apos;m thinking:</p>
                    <ul>
                      <li><strong>Tree-sitter parsing</strong> — break repos into semantic chunks (functions, classes, modules) instead of naive line splits</li>
                      <li><strong>Vector indexing</strong> — embed each chunk through our existing Voyage pipeline, store alongside code metadata</li>
                      <li><strong>Knowledge graph integration</strong> — wire code entities into the graph so agents can traverse function&#8594;file&#8594;module relationships</li>
                      <li><strong>MCP tool</strong> — expose <code>code_search(query)</code> that returns ranked chunks with file paths and line numbers</li>
                      <li><strong>Git-aware re-indexing</strong> — only re-process changed files on each run</li>
                    </ul>
                    <p>This fits cleanly into the existing architecture. MemoryManager for persistence, EventBus for detecting repo changes, search pipeline for retrieval. No parallel infrastructure needed.</p>
                    <p>Tree-sitter covers Python, TypeScript, Go, Rust, Java, C/C++ — I&apos;d start with Python + TypeScript since that covers our own codebase.</p>
                  </div>
                </div>
                <div className="mt-0.5 px-1 text-[10px] text-muted-foreground/60 font-mono">claude-opus-4-6</div>
              </div>
            </div>

            {/* User 3 */}
            <div className="flex gap-3 justify-end">
              <div className="rounded-lg px-3 py-2 text-sm max-w-[80%] bg-primary text-primary-foreground">
                <div className="whitespace-pre-wrap">Love it. Especially the git-aware piece — no point re-indexing the whole repo every time. What does the task breakdown look like?</div>
              </div>
              <div className="mt-1 shrink-0">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
            </div>

            {/* Assistant 3 — with tool call + wrap-up */}
            <div className="flex gap-3 justify-start">
              <div className="mt-1 shrink-0">
                <Bot className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="max-w-[80%]">
                <div className="rounded-lg px-3 py-2 text-sm bg-muted">
                  <div className="my-1 rounded-md border border-border/50 bg-background/30 px-3 py-2 text-xs">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Wrench className="h-3 w-3 shrink-0" />
                      <span className="font-medium text-foreground/80">create work item</span>
                      <span className="opacity-60">&quot;Semantic code indexing for agent codebase navigation&quot;</span>
                    </div>
                    <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[10px] text-muted-foreground">Created epic wi-0040 with 5 subtasks</pre>
                  </div>
                  <div className="prose prose-sm prose-invert max-w-none break-words prose-p:leading-relaxed">
                    <p>I&apos;ve created the epic with five subtasks, prioritized by dependency order:</p>
                    <ol>
                      <li><strong>Tree-sitter parsing layer</strong> (P3) — the foundation, multi-language AST chunking</li>
                      <li><strong>Code chunk embedding pipeline</strong> (P2) — wire into existing Voyage infra</li>
                      <li><strong>Knowledge graph integration</strong> (P2) — code entity relationships</li>
                      <li><strong>MCP tool: code_search()</strong> (P2) — the agent-facing surface</li>
                      <li><strong>Git-aware incremental re-indexing</strong> (P1) — optimization layer</li>
                    </ol>
                    <p>Everything&apos;s lined up and ready to go. Want me to dive in? Just say the word!</p>
                  </div>
                </div>
                <div className="mt-0.5 px-1 text-[10px] text-muted-foreground/60 font-mono">claude-opus-4-6</div>
              </div>
            </div>
          </div>
        </div>

        {/* Input area */}
        <div className="shrink-0 border-t px-4 py-3 md:px-6">
          <div className="mx-auto flex max-w-2xl gap-2">
            <input
              readOnly
              placeholder="Type a message..."
              className={cn(
                "flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm",
                "ring-offset-background placeholder:text-muted-foreground",
              )}
            />
            <Button size="icon">
              <SendHorizonal className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ---------- Real chat drawer ---------- */

export function ChatDrawer({ open, onOpenChange, demo }: ChatDrawerProps) {
  // Demo mode — static content, no runtime
  if (demo) return open ? <DemoChat /> : null;

  // Create adapter instance once — persists for component lifetime
  const adapterRef = useRef<ChatAdapterInstance | null>(null);
  if (!adapterRef.current) {
    adapterRef.current = createChatAdapter();
  }
  const chatAdapter = adapterRef.current;

  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [initialMessages, setInitialMessages] = useState<
    ThreadMessageLike[] | undefined
  >(undefined);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<string>("");

  // Load projects when drawer first opens
  useEffect(() => {
    if (open && projects.length === 0) {
      api.projects({ limit: "100" }).then((r) => setProjects(r.items)).catch(() => {});
    }
  }, [open, projects.length]);

  // Sync project scope to adapter
  useEffect(() => {
    chatAdapter.setProjectScope(activeProject || null);
  }, [activeProject, chatAdapter]);

  const runtime = useLocalRuntime(chatAdapter.adapter, { initialMessages });
  const runtimeRef = useRef(runtime);
  runtimeRef.current = runtime;

  const handleNewChat = useCallback(() => {
    setActiveConvId(null);
    chatAdapter.setConversationId(null);
    setInitialMessages(undefined);
    runtimeRef.current.switchToNewThread();
  }, [chatAdapter]);

  // Wire adapter callbacks
  useEffect(() => {
    chatAdapter.setOnConversationCreated((id) => setActiveConvId(id));
    chatAdapter.setOnStreamComplete(() => { /* no sidebar to refresh */ });
    return () => {
      chatAdapter.setOnConversationCreated(null);
      chatAdapter.setOnStreamComplete(null);
    };
  }, [chatAdapter]);

  // Sync conversation ID to adapter
  useEffect(() => {
    if (!activeConvId) chatAdapter.setConversationId(null);
  }, [activeConvId, chatAdapter]);

  // Reload messages when reopening with an existing conversation
  useEffect(() => {
    if (open && activeConvId) {
      api.conversationMessages(activeConvId).then((r) => {
        const msgs = toThreadMessages(r.messages);
        setInitialMessages(msgs);
        chatAdapter.setConversationId(activeConvId);
      }).catch(() => {});
    }
  }, [open, activeConvId, chatAdapter]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="flex flex-col gap-0 p-0 sm:max-w-xl w-full"
      >
        {/* Accessibility — sr-only */}
        <SheetHeader className="sr-only">
          <SheetTitle>Chat</SheetTitle>
          <SheetDescription>Chat with your Cairn assistant</SheetDescription>
        </SheetHeader>

        <AssistantRuntimeProvider runtime={runtime}>
          {/* Header */}
          <div className="shrink-0 border-b px-4 py-3 pr-12">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageCircle className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-semibold">Chat</span>
                <SingleSelect
                  options={[
                    { value: "", label: "All projects" },
                    ...projects.map((p) => ({ value: p.name, label: p.name })),
                  ]}
                  value={activeProject}
                  onValueChange={setActiveProject}
                  className="h-7 text-xs"
                />
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNewChat}
                className="h-7 px-2 text-xs"
              >
                <RotateCcw className="mr-1 h-3 w-3" />
                New
              </Button>
            </div>
          </div>

          {/* Thread fills remaining height */}
          <div className="flex-1 min-h-0">
            <ChatThread />
          </div>
        </AssistantRuntimeProvider>
      </SheetContent>
    </Sheet>
  );
}
