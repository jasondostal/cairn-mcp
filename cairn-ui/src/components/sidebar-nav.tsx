"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/nav";
import { ChevronRight, LogOut, Moon, Settings, Sun } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useState, useEffect } from "react";
import { NotificationBell } from "@/components/notification-bell";
import { SystemPulse, LS_POSITION_KEY, type SystemPulsePosition } from "@/components/system-pulse";
import { useAuth } from "@/components/auth-provider";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

// Groups that are expanded by default
const DEFAULT_OPEN_GROUPS = new Set(["Core", "Context"]);
const LS_SIDEBAR_GROUPS_KEY = "cairn:sidebar-open-groups";

function useSidebarGroupState() {
  const [openGroups, setOpenGroups] = useState<Set<string>>(DEFAULT_OPEN_GROUPS);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(LS_SIDEBAR_GROUPS_KEY);
      if (stored) setOpenGroups(new Set(JSON.parse(stored)));
    } catch { /* ignore */ }
  }, []);

  const toggle = (label: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      localStorage.setItem(LS_SIDEBAR_GROUPS_KEY, JSON.stringify([...next]));
      return next;
    });
  };

  return { openGroups, toggle };
}

function useVisibilityPolling(pollFn: () => void, intervalMs: number) {
  useEffect(() => {
    let active = true;
    pollFn();
    const id = setInterval(() => {
      if (!document.hidden && active) pollFn();
    }, intervalMs);
    const onVisible = () => {
      if (!document.hidden && active) pollFn();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

function useAttentionCount() {
  const [count, setCount] = useState(0);

  useVisibilityPolling(() => {
    fetch("/api/work-items/gated?limit=1")
      .then((r) => r.json())
      .then((d) => {
        setCount(d.total ?? 0);
      })
      .catch((err) => { console.error("Ready-ids fetch failed", err); });
  }, 30_000);

  return count;
}

function useSidebarMeta() {
  const [time, setTime] = useState("");
  const [version, setVersion] = useState("");

  useEffect(() => {
    const tick = () =>
      setTime(
        new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })
      );
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((d) => setVersion(d.version ?? ""))
      .catch((err) => { console.error("Version fetch failed", err); });
  }, []);

  return { version, time };
}

function getInitials(name: string): string {
  return name
    .split(/[\s_-]+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function useEkgPosition(): SystemPulsePosition {
  const [pos, setPos] = useState<SystemPulsePosition>("header");

  useEffect(() => {
    const stored = localStorage.getItem(LS_POSITION_KEY);
    if (stored === "header" || stored === "footer") setPos(stored);

    function onPosChange(e: Event) {
      const detail = (e as CustomEvent).detail;
      if (detail === "header" || detail === "footer") setPos(detail);
    }
    window.addEventListener("cairn:ekg-position-change", onPosChange);
    return () => window.removeEventListener("cairn:ekg-position-change", onPosChange);
  }, []);

  return pos;
}

export function SidebarNav() {
  const pathname = usePathname();
  const attentionCount = useAttentionCount();
  const { version, time } = useSidebarMeta();
  const { user, authEnabled, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const ekgPosition = useEkgPosition();
  const { openGroups, toggle: toggleGroup } = useSidebarGroupState();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="Cairn">
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/cairn-mark-trail.svg"
                    alt="Cairn"
                    className="size-5"
                  />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-semibold tracking-tight">Cairn</span>
                  {version && (
                    <span className="text-[10px] text-muted-foreground">
                      v{version}
                    </span>
                  )}
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {ekgPosition === "header" && (
            <SidebarMenuItem>
              <SystemPulse />
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {navGroups.map((group) => (
          <Collapsible
            key={group.label}
            open={openGroups.has(group.label)}
            onOpenChange={() => toggleGroup(group.label)}
            className="group/collapsible"
          >
            <SidebarGroup>
              <SidebarGroupLabel asChild>
                <CollapsibleTrigger className="flex w-full items-center">
                  {group.label}
                  <ChevronRight className="ml-auto size-4 transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                </CollapsibleTrigger>
              </SidebarGroupLabel>
              <CollapsibleContent>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {group.items.map(({ href, label, icon: Icon }) => {
                      const active =
                        href === "/"
                          ? pathname === "/"
                          : pathname.startsWith(href);
                      return (
                        <SidebarMenuItem key={href}>
                          <SidebarMenuButton
                            asChild
                            isActive={active}
                            tooltip={label}
                          >
                            <Link href={href}>
                              <Icon className="size-4" />
                              <span>{label}</span>
                            </Link>
                          </SidebarMenuButton>
                          {href === "/work-items" && attentionCount > 0 && (
                            <SidebarMenuBadge className="bg-status-gate text-white rounded-full">
                              {attentionCount}
                            </SidebarMenuBadge>
                          )}
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          {ekgPosition === "footer" && (
            <SidebarMenuItem>
              <SystemPulse />
            </SidebarMenuItem>
          )}
          <SidebarMenuItem>
            <SidebarMenuButton
              size="sm"
              tooltip={theme === "dark" ? "Light mode" : "Dark mode"}
              onClick={toggleTheme}
            >
              {theme === "dark" ? (
                <Sun className="size-4" />
              ) : (
                <Moon className="size-4" />
              )}
              <span>Theme</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <NotificationBell />
          </SidebarMenuItem>
          {authEnabled && user ? (
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton
                    size="lg"
                    tooltip={user.username}
                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  >
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg text-xs">
                        {getInitials(user.username)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid flex-1 text-left text-sm leading-tight">
                      <span className="truncate font-semibold">
                        {user.username}
                      </span>
                      {user.role && (
                        <span className="truncate text-xs text-muted-foreground">
                          {user.role}
                        </span>
                      )}
                    </div>
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                  side="top"
                  align="end"
                  sideOffset={4}
                >
                  <DropdownMenuItem asChild>
                    <Link href="/settings" className="gap-2">
                      <Settings className="size-4" />
                      Settings
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout} className="gap-2">
                    <LogOut className="size-4" />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          ) : (
            <SidebarMenuItem>
              <SidebarMenuButton size="sm" asChild tooltip="Settings">
                <Link href="/settings">
                  <Settings className="size-4" />
                  <span>Settings</span>
                  {time && (
                    <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
                      {time}
                    </span>
                  )}
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
