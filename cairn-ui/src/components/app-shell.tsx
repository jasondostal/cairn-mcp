"use client";

import { usePathname } from "next/navigation";
import { SidebarNav } from "@/components/sidebar-nav";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
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
      <SidebarProvider>
        <SidebarNav />
        <SidebarInset className="h-dvh overflow-hidden">
          {/* Mobile-only header — hidden on desktop where icons live in sidebar */}
          <header className="flex h-10 shrink-0 items-center gap-2 border-b px-4 md:hidden">
            <SidebarTrigger className="-ml-1" />
          </header>
          <div id="main-content" className="flex-1 min-h-0 overflow-y-auto p-4 md:p-6">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </SidebarInset>
      </SidebarProvider>
      <CommandPalette />
      <ChatDrawerTrigger />
    </>
  );
}
