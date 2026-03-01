"use client";

import { usePathname } from "next/navigation";
import { SidebarNav } from "@/components/sidebar-nav";
import { CommandPalette } from "@/components/command-palette";
import { ChatDrawerTrigger } from "@/components/chat/chat-drawer-trigger";
import { ErrorBoundary } from "@/components/error-boundary";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <>
      <div className="flex h-dvh flex-col md:flex-row">
        <SidebarNav />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
      <CommandPalette />
      <ChatDrawerTrigger />
    </>
  );
}
