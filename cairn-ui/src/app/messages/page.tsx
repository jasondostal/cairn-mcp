"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Message } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import {
  Mail,
  MailOpen,
  Archive,
  CheckCheck,
  Send,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(dateStr).getTime()) / 1000
  );
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function senderLabel(sender: string): string {
  if (sender === "user") return "You";
  if (sender === "assistant") return "Chat";
  return sender;
}

function senderColor(sender: string): string {
  if (sender === "user") return "bg-blue-500/15 text-blue-600 dark:text-blue-400";
  if (sender === "assistant") return "bg-violet-500/15 text-violet-600 dark:text-violet-400";
  return "bg-orange-500/15 text-orange-600 dark:text-orange-400";
}

function MessageRow({
  message,
  showProject,
  onMarkRead,
  onArchive,
}: {
  message: Message;
  showProject?: boolean;
  onMarkRead: (id: number) => void;
  onArchive: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const unread = !message.is_read;
  const urgent = message.priority === "urgent";

  return (
    <Card
      className={cn(
        "transition-colors",
        unread && "border-l-2 border-l-primary",
        urgent && unread && "border-l-red-500",
      )}
    >
      <CardContent className="p-4">
        <div
          className="flex items-start gap-3 cursor-pointer"
          onClick={() => {
            setExpanded(!expanded);
            if (unread) onMarkRead(message.id);
          }}
        >
          <div className="mt-0.5 shrink-0">
            {unread ? (
              <Mail className={cn("h-4 w-4", urgent ? "text-red-500" : "text-primary")} />
            ) : (
              <MailOpen className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 min-w-0 space-y-1">
            <p className={cn("text-sm", unread && "font-medium")}>
              {expanded ? message.content : message.content.length > 120 ? message.content.slice(0, 120) + "..." : message.content}
            </p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
              <Badge variant="secondary" className={cn("text-xs", senderColor(message.sender))}>
                {senderLabel(message.sender)}
              </Badge>
              {showProject && message.project && (
                <Badge variant="secondary" className="text-xs">
                  {message.project}
                </Badge>
              )}
              {urgent && (
                <Badge variant="destructive" className="text-xs gap-1">
                  <AlertCircle className="h-3 w-3" />
                  urgent
                </Badge>
              )}
              <span>{timeAgo(message.created_at)}</span>
              <span className="hidden sm:inline">{formatDate(message.created_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {unread && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                title="Mark read"
                onClick={(e) => {
                  e.stopPropagation();
                  onMarkRead(message.id);
                }}
              >
                <CheckCheck className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              title="Archive"
              onClick={(e) => {
                e.stopPropagation();
                onArchive(message.id);
              }}
            >
              <Archive className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MessageDenseRow({
  message,
  showProject,
  onMarkRead,
  onArchive,
}: {
  message: Message;
  showProject?: boolean;
  onMarkRead: (id: number) => void;
  onArchive: (id: number) => void;
}) {
  const unread = !message.is_read;
  const urgent = message.priority === "urgent";

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer",
        unread && "font-medium",
      )}
      onClick={() => {
        if (unread) onMarkRead(message.id);
      }}
    >
      <div className="shrink-0">
        {unread ? (
          <Mail className={cn("h-3.5 w-3.5", urgent ? "text-red-500" : "text-primary")} />
        ) : (
          <MailOpen className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </div>
      <Badge variant="secondary" className={cn("text-xs shrink-0", senderColor(message.sender))}>
        {senderLabel(message.sender)}
      </Badge>
      <span className="flex-1 truncate">{message.content}</span>
      {showProject && message.project && (
        <Badge variant="secondary" className="text-xs shrink-0">{message.project}</Badge>
      )}
      {urgent && (
        <Badge variant="destructive" className="text-xs shrink-0">urgent</Badge>
      )}
      <span className="text-xs text-muted-foreground shrink-0">{timeAgo(message.created_at)}</span>
      <div className="flex items-center gap-1 shrink-0">
        {unread && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            title="Mark read"
            onClick={(e) => {
              e.stopPropagation();
              onMarkRead(message.id);
            }}
          >
            <CheckCheck className="h-3 w-3" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          title="Archive"
          onClick={(e) => {
            e.stopPropagation();
            onArchive(message.id);
          }}
        >
          <Archive className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

function ComposeArea({
  projects,
  onSend,
}: {
  projects: Array<{ name: string }>;
  onSend: () => void;
}) {
  const [content, setContent] = useState("");
  const [project, setProject] = useState(projects[0]?.name || "");
  const [priority, setPriority] = useState<"normal" | "urgent">("normal");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!project && projects.length > 0) setProject(projects[0].name);
  }, [projects, project]);

  const handleSend = async () => {
    if (!content.trim() || !project) return;
    setSending(true);
    try {
      await api.sendMessage({ content: content.trim(), project, sender: "user", priority });
      setContent("");
      setPriority("normal");
      onSend();
    } catch (err) {
      toast.error("Failed to send message", {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <textarea
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
          rows={2}
          placeholder="Leave a message..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
          }}
        />
        <div className="flex items-center gap-2 flex-wrap">
          <select
            className="rounded-md border border-input bg-background px-2 py-1 text-sm"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
          <Button
            variant={priority === "urgent" ? "destructive" : "outline"}
            size="sm"
            onClick={() => setPriority(priority === "urgent" ? "normal" : "urgent")}
          >
            {priority === "urgent" ? "Urgent" : "Normal"}
          </Button>
          <Button
            size="sm"
            disabled={!content.trim() || !project || sending}
            onClick={handleSend}
            className="ml-auto gap-1"
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MessagesPage() {
  const filters = usePageFilters();
  const [messages, setMessages] = useState<Message[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const loadMessages = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .messages({
        project: filters.showAllProjects ? undefined : filters.projectFilter.join(","),
        include_archived: showArchived ? "true" : undefined,
        limit: "50",
      })
      .then((r) => {
        setMessages(r.items);
        setTotal(r.total);
      })
      .catch((err) => setError(err?.message || "Failed to load messages"))
      .finally(() => setLoading(false));
  }, [filters.projectFilter, showArchived, filters.showAllProjects]);

  useEffect(() => {
    loadMessages();
    const id = setInterval(loadMessages, 15_000);
    return () => clearInterval(id);
  }, [loadMessages]);

  const handleMarkRead = async (id: number) => {
    await api.updateMessage(id, { is_read: true });
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, is_read: true } : m))
    );
  };

  const handleArchive = async (id: number) => {
    await api.updateMessage(id, { archived: true });
    setMessages((prev) => prev.filter((m) => m.id !== id));
    setTotal((t) => Math.max(0, t - 1));
  };

  const handleMarkAllRead = async () => {
    const proj = filters.showAllProjects ? undefined : filters.projectFilter.join(",");
    await api.markAllMessagesRead(proj);
    setMessages((prev) => prev.map((m) => ({ ...m, is_read: true })));
  };

  const unreadCount = messages.filter((m) => !m.is_read).length;

  return (
    <PageLayout
      title="Messages"
      titleExtra={
        <div className="flex items-center gap-2">
          <DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />
          {unreadCount > 0 && (
            <Button variant="outline" size="sm" onClick={handleMarkAllRead} className="gap-1">
              <CheckCheck className="h-3.5 w-3.5" />
              Mark all read
            </Button>
          )}
        </div>
      }
      filters={
        <PageFilters
          filters={filters}
          extra={
            <>
              <Button
                variant={showArchived ? "default" : "outline"}
                size="sm"
                onClick={() => setShowArchived(!showArchived)}
              >
                {showArchived ? "Hide" : "Show"} archived
              </Button>
              {total > 0 && (
                <span className="text-xs text-muted-foreground ml-auto">
                  {total} message{total !== 1 ? "s" : ""}
                  {unreadCount > 0 && ` (${unreadCount} unread)`}
                </span>
              )}
            </>
          }
        />
      }
    >
      <div className="space-y-4">
        {!filters.projectsLoading && filters.projects.length > 0 && (
          <ComposeArea projects={filters.projects} onSend={loadMessages} />
        )}

        {(loading && messages.length === 0) || filters.projectsLoading ? (
          <SkeletonList count={4} height="h-20" />
        ) : error ? (
          <ErrorState message="Failed to load messages" detail={error} />
        ) : messages.length === 0 ? (
          <EmptyState
            message={filters.showAllProjects ? "No messages yet." : `No messages for ${filters.projectFilter.join(", ")}.`}
            detail="Messages from agents and users will appear here."
          />
        ) : filters.dense ? (
          <div className="rounded-md border border-border divide-y divide-border">
            {messages.map((m) => (
              <MessageDenseRow
                key={m.id}
                message={m}
                showProject={filters.showAllProjects}
                onMarkRead={handleMarkRead}
                onArchive={handleArchive}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {messages.map((m) => (
              <MessageRow
                key={m.id}
                message={m}
                showProject={filters.showAllProjects}
                onMarkRead={handleMarkRead}
                onArchive={handleArchive}
              />
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
