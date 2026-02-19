"use client";

import { Suspense, useState, useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatDrawer } from "./chat-drawer";

function ChatDrawerTriggerInner() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Hide on the full chat page — redundant there
  const isOnChatPage = pathname === "/chat";

  // Demo mode: ?demo=true auto-opens with static content
  const isDemo = searchParams.get("demo") === "true";

  useEffect(() => {
    if (isDemo && !isOnChatPage) {
      setOpen(true);
    }
  }, [isDemo, isOnChatPage]);

  // Keyboard shortcut: Cmd+. (or Ctrl+.) to toggle
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === ".") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  if (isOnChatPage) return null;

  return (
    <>
      <Button
        size="icon"
        variant="outline"
        className="fixed bottom-4 right-4 z-40 h-10 w-10 rounded-full shadow-lg
                   bg-background/80 backdrop-blur-sm hover:bg-accent
                   md:bottom-6 md:right-6"
        onClick={() => setOpen(true)}
        title="Open chat (Cmd+.)"
      >
        <MessageCircle className="h-5 w-5" />
      </Button>

      <ChatDrawer open={open} onOpenChange={setOpen} demo={isDemo} />
    </>
  );
}

export function ChatDrawerTrigger() {
  return (
    <Suspense>
      <ChatDrawerTriggerInner />
    </Suspense>
  );
}
