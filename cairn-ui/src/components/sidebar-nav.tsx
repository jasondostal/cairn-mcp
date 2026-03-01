"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { navGroups } from "@/lib/nav";
import {
  Menu,
  X,
} from "lucide-react";
import { useState, useEffect } from "react";
import { NotificationBell } from "@/components/notification-bell";

function useVisibilityPolling(pollFn: () => void, intervalMs: number) {
  useEffect(() => {
    let active = true;
    pollFn();
    const id = setInterval(() => {
      if (!document.hidden && active) pollFn();
    }, intervalMs);
    const onVisible = () => { if (!document.hidden && active) pollFn(); };
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
      .catch(() => {});
  }, 30_000);

  return count;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const attentionCount = useAttentionCount();

  return (
    <>
      {navGroups.map((group, gi) => (
        <div key={group.label} className={cn(gi > 0 && "mt-1.5 pt-1.5")}>
          {gi > 0 && <div className="mx-auto mb-1.5 h-px w-8 rounded-full bg-border/30" />}
          {group.items.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
                {href === "/work-items" && attentionCount > 0 && (
                  <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-status-gate px-1.5 text-[11px] font-medium leading-none text-white">
                    {attentionCount}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}

function useSidebarMeta() {
  const [time, setTime] = useState("");
  const [version, setVersion] = useState("");

  useEffect(() => {
    const tick = () =>
      setTime(
        new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((d) => setVersion(d.version ?? ""))
      .catch(() => {});
  }, []);

  return { version, time };
}

export function SidebarNav() {
  const [open, setOpen] = useState(false);
  const { version, time } = useSidebarMeta();

  return (
    <>
      {/* Mobile header */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-card px-4 md:hidden">
        <Link href="/" className="flex items-center gap-2 rounded-md px-1 -mx-1 hover:bg-accent/30 transition-colors">
          <img src="/cairn-mark-trail.svg" alt="Cairn" className="h-5 w-5" />
          <span className="text-lg font-semibold tracking-tight">Cairn</span>
        </Link>
        <div className="flex items-center gap-1">
          <NotificationBell />
          <button
            onClick={() => setOpen(!open)}
            className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </header>

      {/* Mobile drawer */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setOpen(false)}
        >
          <aside
            className="fixed inset-y-0 left-0 z-50 w-56 border-r border-border bg-card pt-14"
            onClick={(e) => e.stopPropagation()}
          >
            <nav className="flex flex-col gap-1 p-2">
              <NavLinks onNavigate={() => setOpen(false)} />
            </nav>
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card md:flex">
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <Link href="/" className="flex items-center gap-2 rounded-md px-1 -mx-1 hover:bg-accent/30 transition-colors">
            <img src="/cairn-mark-trail.svg" alt="Cairn" className="h-5 w-5" />
            <span className="text-lg font-semibold tracking-tight">Cairn</span>
          </Link>
          <div className="flex items-center gap-1.5">
            <NotificationBell />
            <div className="text-[10px] text-muted-foreground/50 tabular-nums text-right leading-tight">
              {version && <div>v{version}</div>}
              {time && <div>{time}</div>}
            </div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col p-2 overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border/40 hover:scrollbar-thumb-border/60"
          style={{ scrollbarWidth: "thin", scrollbarColor: "hsl(var(--border) / 0.4) transparent" }}>
          <NavLinks />
        </nav>
      </aside>
    </>
  );
}
