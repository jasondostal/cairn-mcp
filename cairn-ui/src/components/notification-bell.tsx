"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Notification, type NotificationSeverity } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSSE } from "@/hooks/use-sse";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  Bell,
  Check,
  CheckCircle,
  Info,
  TriangleAlert,
  X,
} from "lucide-react";

const POLL_INTERVAL = 15_000;

const severityIcon: Record<NotificationSeverity, typeof Info> = {
  info: Info,
  warning: TriangleAlert,
  error: AlertCircle,
  success: CheckCircle,
};

const severityColor: Record<NotificationSeverity, string> = {
  info: "text-[oklch(0.488_0.243_264)]",
  warning: "text-[oklch(0.769_0.188_70)]",
  error: "text-destructive",
  success: "text-[oklch(0.696_0.17_162)]",
};

export function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  // Fetch full list when drawer opens
  const fetchNotifications = useCallback(() => {
    setLoading(true);
    api.notifications({ limit: "30" })
      .then((d) => {
        setNotifications(d.items);
        setUnread(d.unread);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // SSE for real-time notification events — bump unread on new notifications
  const { connected: sseConnected } = useSSE("notification.*", {
    onEvent: () => {
      api.unreadCount()
        .then((d) => setUnread(d.unread))
        .catch(() => {});
      if (open) fetchNotifications();
    },
  });

  // Polling fallback when SSE is disconnected
  useEffect(() => {
    if (sseConnected) return;
    let active = true;
    function poll() {
      if (document.hidden || !active) return;
      api.unreadCount()
        .then((d) => { if (active) setUnread(d.unread); })
        .catch(() => {});
    }
    poll();
    const id = setInterval(poll, POLL_INTERVAL);
    const onVisible = () => { if (!document.hidden) poll(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [sseConnected]);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  async function handleMarkRead(id: number) {
    await api.markNotificationRead(id).catch(() => {});
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
    );
    setUnread((prev) => Math.max(0, prev - 1));
  }

  async function handleMarkAllRead() {
    await api.markAllNotificationsRead().catch(() => {});
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnread(0);
  }

  function handleClick(n: Notification) {
    if (!n.is_read) handleMarkRead(n.id);
    // Navigate to source if possible
    const workItemId = n.metadata?.work_item_id;
    if (workItemId) {
      setOpen(false);
      router.push(`/work-items?open=${workItemId}`);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="relative rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        title={unread > 0 ? `${unread} unread notifications` : "Notifications"}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[oklch(0.645_0.246_16)] px-1 text-[10px] font-medium leading-none text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto w-80 sm:w-96">
          <SheetHeader>
            <div className="flex items-center justify-between">
              <SheetTitle className="text-base">
                Notifications
                {unread > 0 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {unread} unread
                  </span>
                )}
              </SheetTitle>
              {unread > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleMarkAllRead}
                  className="text-xs h-7"
                >
                  <Check className="mr-1 h-3 w-3" />
                  Mark all read
                </Button>
              )}
            </div>
          </SheetHeader>

          <div className="mt-2">
            {loading && notifications.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">Loading...</p>
            )}

            {!loading && notifications.length === 0 && (
              <div className="text-center py-8">
                <Bell className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No notifications yet</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Create event subscriptions to start receiving notifications.
                </p>
              </div>
            )}

            <div className="space-y-0.5">
              {notifications.map((n) => {
                const Icon = severityIcon[n.severity] || Info;
                const color = severityColor[n.severity] || severityColor.info;

                return (
                  <div
                    key={n.id}
                    onClick={() => handleClick(n)}
                    className={`flex items-start gap-2.5 rounded-md px-3 py-2.5 cursor-pointer transition-colors ${
                      n.is_read
                        ? "opacity-60 hover:opacity-80 hover:bg-accent/30"
                        : "hover:bg-accent/50"
                    }`}
                  >
                    <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${color}`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-tight ${n.is_read ? "" : "font-medium"}`}>
                        {n.title}
                      </p>
                      {n.body && (
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                          {n.body}
                        </p>
                      )}
                      <p className="text-[10px] text-muted-foreground/60 mt-1">
                        {formatDateTime(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <span className="h-2 w-2 rounded-full bg-[oklch(0.488_0.243_264)] shrink-0 mt-1.5" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
