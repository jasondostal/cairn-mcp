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

function useUnreadCount() {
  const [count, setCount] = useState(0);
  const [hasUrgent, setHasUrgent] = useState(false);

  useEffect(() => {
    let active = true;
    const poll = () => {
      fetch("/api/messages/unread-count")
        .then((r) => r.json())
        .then((d) => {
          if (!active) return;
          setCount(d.count ?? 0);
        })
        .catch(() => {});
      fetch("/api/messages?limit=1&include_archived=false")
        .then((r) => r.json())
        .then((d) => {
          if (!active) return;
          const items = d.items ?? [];
          setHasUrgent(items.some((m: { priority: string; is_read: boolean }) => m.priority === "urgent" && !m.is_read));
        })
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 30_000);
    return () => { active = false; clearInterval(id); };
  }, []);

  return { count, hasUrgent };
}

function useAttentionCount() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let active = true;
    const poll = () => {
      fetch("/api/work-items/gated?limit=1")
        .then((r) => r.json())
        .then((d) => {
          if (!active) return;
          setCount(d.total ?? 0);
        })
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 30_000);
    return () => { active = false; clearInterval(id); };
  }, []);

  return count;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { count: unreadCount, hasUrgent } = useUnreadCount();
  const attentionCount = useAttentionCount();

  return (
    <>
      {navGroups.map((group, gi) => (
        <div key={group.label} className={cn(gi > 0 && "mt-4")}>
          <div className="px-3 pb-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50">
            {group.label}
          </div>
          {group.items.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
                {href === "/work-items" && attentionCount > 0 && (
                  <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[oklch(0.627_0.265_304)] px-1.5 text-[11px] font-medium leading-none text-white">
                    {attentionCount}
                  </span>
                )}
                {href === "/messages" && unreadCount > 0 && (
                  <span
                    className={cn(
                      "ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-medium leading-none text-white",
                      hasUrgent ? "bg-red-500" : "bg-primary"
                    )}
                  >
                    {unreadCount}
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

function SidebarFooter() {
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

  return (
    <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground/60 tabular-nums">
      {version && <span>v{version}</span>}
      {time && <span className="float-right">{time}</span>}
    </div>
  );
}

export function SidebarNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile header */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-card px-4 md:hidden">
        <Link href="/" className="flex items-center gap-2 rounded-md px-1 -mx-1 hover:bg-accent/30 transition-colors">
          <img src="/cairn-mark-trail.svg" alt="Cairn" className="h-5 w-5" />
          <span className="text-lg font-semibold tracking-tight">Cairn</span>
        </Link>
        <button
          onClick={() => setOpen(!open)}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
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
        <div className="flex h-14 items-center border-b border-border px-4">
          <Link href="/" className="flex items-center gap-2 rounded-md px-1 -mx-1 hover:bg-accent/30 transition-colors">
            <img src="/cairn-mark-trail.svg" alt="Cairn" className="h-5 w-5" />
            <span className="text-lg font-semibold tracking-tight">Cairn</span>
          </Link>
        </div>
        <nav className="flex flex-1 flex-col p-2 overflow-y-auto">
          <NavLinks />
        </nav>
        <SidebarFooter />
      </aside>
    </>
  );
}
