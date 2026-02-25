"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api, type Conversation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  MessageSquarePlus,
  Trash2,
  MessageCircle,
  Loader2,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ConversationSidebarProps {
  activeId: number | null;
  onSelect: (conv: Conversation) => void;
  onNew: () => void;
  refreshKey?: number;
  /** Filter conversations to this project. Empty/undefined = all projects. */
  project?: string;
  /** Compact spacing for drawer context. */
  compact?: boolean;
}

export function ConversationSidebar({
  activeId,
  onSelect,
  onNew,
  refreshKey,
  project,
  compact,
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

  const load = useCallback(async () => {
    try {
      const opts: Record<string, string> = { limit: "50" };
      if (project) opts.project = project;
      const result = await api.conversations(opts);
      setConversations(result.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load, refreshKey]);

  // Refresh when active conversation changes (e.g., after auto-title)
  useEffect(() => {
    if (activeId) {
      const timer = setTimeout(load, 2000);
      return () => clearTimeout(timer);
    }
  }, [activeId, load]);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.deleteConversation(deleteTarget.id);
      setConversations((prev) => prev.filter((c) => c.id !== deleteTarget.id));
      if (activeId === deleteTarget.id) {
        onNew();
      }
    } catch {
      // silent
    } finally {
      setDeleteTarget(null);
    }
  };

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter(
      (c) => (c.title || "").toLowerCase().includes(q),
    );
  }, [conversations, searchQuery]);

  // Show project labels when not filtering by a specific project
  const showProjectLabels = !project;

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  return (
    <div className="flex h-full flex-col border-r">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-xs font-medium text-muted-foreground">
          History
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onNew}
          title="New conversation"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Search */}
      <div className="px-2 py-1.5 border-b">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border bg-background pl-7 pr-2 py-1 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">
            {searchQuery ? "No matches" : "No conversations yet"}
          </div>
        ) : (
          <div className="py-1">
            {filtered.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelect(conv)}
                className={cn(
                  "group flex w-full items-start gap-2 px-3 text-left text-sm hover:bg-muted/50 transition-colors",
                  compact ? "py-1.5" : "py-2",
                  activeId === conv.id && "bg-muted",
                )}
              >
                <MessageCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium">
                    {conv.title || "Untitled"}
                  </div>
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <span>{formatDate(conv.updated_at)}</span>
                    {conv.message_count > 0 && (
                      <>
                        <span>&middot;</span>
                        <span>{conv.message_count} msgs</span>
                      </>
                    )}
                    {showProjectLabels && conv.project && (
                      <>
                        <span>&middot;</span>
                        <span className="truncate max-w-[60px]">{conv.project}</span>
                      </>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteTarget(conv);
                  }}
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3 text-muted-foreground" />
                </Button>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleteTarget?.title || "Untitled"}&rdquo; and all its messages will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
