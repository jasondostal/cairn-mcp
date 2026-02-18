"use client";

import { forwardRef, useRef, useEffect } from "react";
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useMessage,
  useThreadRuntime,
  type TextMessagePartProps,
  type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import {
  Bot,
  User,
  SendHorizonal,
  Square,
  Wrench,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SearchToolUI } from "./tools/search-tool-ui";
import { RecallToolUI } from "./tools/recall-tool-ui";
import { StoreToolUI } from "./tools/store-tool-ui";
import { StatusToolUI } from "./tools/status-tool-ui";
import {
  ListWorkItemsToolUI,
  CreateWorkItemToolUI,
} from "./tools/work-items-tool-ui";

/* ---------- Markdown text renderer ---------- */

function MarkdownText() {
  return (
    <MarkdownTextPrimitive
      className="prose prose-sm prose-invert max-w-none break-words
        prose-p:leading-relaxed prose-pre:bg-background/50 prose-pre:border
        prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
        prose-headings:text-foreground prose-a:text-primary"
    />
  );
}

/* ---------- Tool call fallback renderer ---------- */

function ToolCallFallback({
  toolName,
  args,
  result,
  status,
}: ToolCallMessagePartProps) {
  const displayName = toolName.replace(/_/g, " ");
  const inputSummary = getToolInputSummary(toolName, args);
  const isComplete = status.type === "complete";

  return (
    <div className="my-1 rounded-md border border-border/50 bg-background/30 px-3 py-2 text-xs">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Wrench className="h-3 w-3 shrink-0" />
        <span className="font-medium text-foreground/80">{displayName}</span>
        {inputSummary && <span className="opacity-60">{inputSummary}</span>}
        {!isComplete && (
          <span className="ml-auto animate-pulse text-[10px]">running...</span>
        )}
      </div>
      {isComplete && result !== undefined && (
        <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[10px] text-muted-foreground">
          {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}

function getToolInputSummary(
  name: string,
  input: Record<string, unknown>,
): string {
  if (name === "search_memories" && input.query)
    return `"${input.query}"`;
  if (name === "recall_memory" && input.ids)
    return `#${(input.ids as number[]).join(", #")}`;
  if (name === "store_memory" && input.project)
    return `in ${input.project}`;
  if (name === "list_tasks" && input.project) return `${input.project}`;
  if (name === "get_rules" && input.project) return `${input.project}`;
  if (name === "list_work_items") return input.status ? `${input.status}` : "";
  if (name === "create_work_item" && input.title)
    return `"${input.title}"`;
  return "";
}

/* ---------- User message ---------- */

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex gap-3 justify-end">
      <div className="rounded-lg px-3 py-2 text-sm max-w-[80%] bg-primary text-primary-foreground">
        <MessagePrimitive.Content
          components={{ Text: UserText }}
        />
      </div>
      <div className="mt-1 shrink-0">
        <User className="h-5 w-5 text-muted-foreground" />
      </div>
    </MessagePrimitive.Root>
  );
}

function UserText({ text }: TextMessagePartProps) {
  return <div className="whitespace-pre-wrap">{text}</div>;
}

/* ---------- Assistant message ---------- */

function AssistantMessage() {
  const message = useMessage();
  const model = (message?.metadata?.custom as Record<string, unknown>)?.model as string | undefined;

  return (
    <MessagePrimitive.Root className="flex gap-3 justify-start">
      <div className="mt-1 shrink-0">
        <Bot className="h-5 w-5 text-muted-foreground" />
      </div>
      <div className="max-w-[80%]">
        <div className="rounded-lg px-3 py-2 text-sm bg-muted">
          <MessagePrimitive.Content
            components={{
              Text: MarkdownText,
              tools: {
                by_name: {
                  search_memories: SearchToolUI,
                  recall_memory: RecallToolUI,
                  store_memory: StoreToolUI,
                  system_status: StatusToolUI,
                  list_work_items: ListWorkItemsToolUI,
                  create_work_item: CreateWorkItemToolUI,
                },
                Fallback: ToolCallFallback,
              },
            }}
          />
        </div>
        {model && (
          <div className="mt-0.5 px-1 text-[10px] text-muted-foreground/60 font-mono">
            {model}
          </div>
        )}
      </div>
    </MessagePrimitive.Root>
  );
}

/* ---------- Composer ---------- */

const ChatComposer = forwardRef<HTMLFormElement>(function ChatComposer(_, ref) {
  return (
    <ComposerPrimitive.Root
      ref={ref}
      className="mx-auto flex max-w-2xl gap-2"
    >
      <ComposerPrimitive.Input
        autoFocus
        placeholder="Type a message..."
        rows={1}
        className={cn(
          "flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm",
          "ring-offset-background placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      />
      <ComposerPrimitive.Send asChild>
        <Button size="icon">
          <SendHorizonal className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Send>
      <ComposerPrimitive.Cancel asChild>
        <Button size="icon" variant="ghost">
          <Square className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Cancel>
    </ComposerPrimitive.Root>
  );
});

/* ---------- Scroll to bottom ---------- */

function ScrollToBottom() {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <Button
        size="icon"
        variant="outline"
        className="absolute bottom-2 right-4 h-8 w-8 rounded-full shadow-md"
      >
        <ChevronDown className="h-4 w-4" />
      </Button>
    </ThreadPrimitive.ScrollToBottom>
  );
}

/* ---------- Empty state ---------- */

function EmptyState() {
  return (
    <ThreadPrimitive.Empty>
      <div className="flex h-full items-center justify-center">
        <div className="text-center text-muted-foreground">
          <Bot className="mx-auto mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">Talk to your Cairn LLM.</p>
          <p className="mt-1 text-xs opacity-60">
            The assistant can search and browse your memories.
          </p>
        </div>
      </div>
    </ThreadPrimitive.Empty>
  );
}

/* ---------- Main thread layout ---------- */

interface ChatThreadProps {
  onFirstMessage?: () => void;
}

export function ChatThread({ onFirstMessage }: ChatThreadProps) {
  const runtime = useThreadRuntime();
  const calledRef = useRef(false);

  useEffect(() => {
    return runtime.subscribe(() => {
      const msgs = runtime.getState().messages;
      if (msgs.length > 0 && !calledRef.current) {
        calledRef.current = true;
        onFirstMessage?.();
      }
    });
  }, [runtime, onFirstMessage]);

  // Reset when thread changes (new runtime subscription = new calledRef)
  useEffect(() => {
    calledRef.current = false;
  }, [runtime]);

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-4 py-4 md:px-6">
        <EmptyState />
        <div className="mx-auto max-w-2xl space-y-4">
          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              AssistantMessage,
            }}
          />
        </div>
        <ScrollToBottom />
      </ThreadPrimitive.Viewport>

      {/* Input area */}
      <div className="shrink-0 border-t px-4 py-3 md:px-6">
        <ChatComposer />
      </div>
    </ThreadPrimitive.Root>
  );
}
