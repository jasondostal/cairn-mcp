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
import { RotateCcw, MessageCircle } from "lucide-react";

interface ChatDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChatDrawer({ open, onOpenChange }: ChatDrawerProps) {
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
        side="right"
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
