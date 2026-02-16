"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type WorkItemDetail, type WorkItemStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { StatusDot, StatusText, PriorityDots } from "./status-dot";
import {
  CheckCircle,
  ChevronRight,
  GitBranch,
  Link2,
  Lock,
  User,
  XCircle,
} from "lucide-react";

interface WorkItemSheetProps {
  itemId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAction?: () => void;
  onNavigate?: (id: number) => void;
}

export function WorkItemSheet({
  itemId,
  open,
  onOpenChange,
  onAction,
  onNavigate,
}: WorkItemSheetProps) {
  const [detail, setDetail] = useState<WorkItemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    if (!itemId || !open) return;
    setLoading(true);
    api.workItem(itemId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [itemId, open]);

  async function handleComplete() {
    if (!detail) return;
    setActing(true);
    try {
      await api.workItemComplete(detail.id);
      onAction?.();
      onOpenChange(false);
    } catch { /* stays open on error */ }
    finally { setActing(false); }
  }

  async function handleClaim() {
    if (!detail) return;
    setActing(true);
    try {
      await api.workItemClaim(detail.id, "user");
      // Refresh detail
      const updated = await api.workItem(detail.id);
      setDetail(updated);
      onAction?.();
    } catch { /* silent */ }
    finally { setActing(false); }
  }

  async function handleCancel() {
    if (!detail) return;
    setActing(true);
    try {
      await api.workItemUpdate(detail.id, { status: "cancelled" });
      onAction?.();
      onOpenChange(false);
    } catch { /* silent */ }
    finally { setActing(false); }
  }

  function navigateTo(id: number) {
    onNavigate?.(id);
  }

  const isTerminal = detail?.status === "done" || detail?.status === "cancelled";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto">
        {loading && (
          <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
            Loading...
          </div>
        )}
        {!loading && detail && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2 flex-wrap">
                <StatusDot status={detail.status} className="h-2.5 w-2.5" />
                <StatusText status={detail.status} />
                <Badge variant="outline" className="font-mono text-xs">
                  {detail.item_type}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  {detail.project}
                </Badge>
                <PriorityDots priority={detail.priority} />
              </div>
              <SheetTitle className="font-mono text-lg">
                {detail.short_id}
              </SheetTitle>
              <SheetDescription className="text-sm text-foreground">
                {detail.title}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              <Separator />

              {/* Description */}
              {detail.description && (
                <div>
                  <SectionHeader>Description</SectionHeader>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {detail.description}
                  </p>
                </div>
              )}

              {/* Acceptance Criteria */}
              {detail.acceptance_criteria && (
                <div>
                  <SectionHeader>Acceptance Criteria</SectionHeader>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {detail.acceptance_criteria}
                  </p>
                </div>
              )}

              {/* Assignee */}
              {detail.assignee && (
                <div className="flex items-center gap-2 text-sm">
                  <User className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-mono text-muted-foreground">@{detail.assignee}</span>
                </div>
              )}

              {/* Hierarchy */}
              {(detail.parent || detail.children_count > 0) && (
                <>
                  <Separator />
                  <div>
                    <SectionHeader icon={<GitBranch className="h-3 w-3" />}>
                      Hierarchy
                    </SectionHeader>
                    {detail.parent && (
                      <div className="mb-2">
                        <span className="text-xs text-muted-foreground mr-2">Parent:</span>
                        <button
                          onClick={() => navigateTo(detail.parent!.id)}
                          className="text-sm text-primary hover:underline font-mono"
                        >
                          {detail.parent.short_id}
                        </button>
                        <span className="text-sm text-muted-foreground ml-2">{detail.parent.title}</span>
                      </div>
                    )}
                    {detail.children_count > 0 && (
                      <div className="text-xs text-muted-foreground">
                        {detail.children_count} child{detail.children_count !== 1 ? "ren" : ""}
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Dependencies */}
              {(detail.blockers.length > 0 || detail.blocking.length > 0) && (
                <>
                  <Separator />
                  <div>
                    <SectionHeader icon={<Lock className="h-3 w-3" />}>
                      Dependencies
                    </SectionHeader>
                    {detail.blockers.length > 0 && (
                      <div className="mb-2">
                        <span className="text-xs text-muted-foreground block mb-1">Blocked by:</span>
                        <div className="space-y-1">
                          {detail.blockers.map((b) => (
                            <div key={b.id} className="flex items-center gap-2 text-sm">
                              <StatusDot status={b.status as WorkItemStatus} />
                              <button
                                onClick={() => navigateTo(b.id)}
                                className="font-mono text-xs text-primary hover:underline"
                              >
                                {b.short_id}
                              </button>
                              <span className="truncate text-muted-foreground">{b.title}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {detail.blocking.length > 0 && (
                      <div>
                        <span className="text-xs text-muted-foreground block mb-1">Blocking:</span>
                        <div className="space-y-1">
                          {detail.blocking.map((b) => (
                            <div key={b.id} className="flex items-center gap-2 text-sm">
                              <StatusDot status={b.status as WorkItemStatus} />
                              <button
                                onClick={() => navigateTo(b.id)}
                                className="font-mono text-xs text-primary hover:underline"
                              >
                                {b.short_id}
                              </button>
                              <span className="truncate text-muted-foreground">{b.title}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Linked Memories */}
              {detail.linked_memories.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <SectionHeader icon={<Link2 className="h-3 w-3" />}>
                      Linked Memories ({detail.linked_memories.length})
                    </SectionHeader>
                    <div className="space-y-1.5">
                      {detail.linked_memories.map((m) => (
                        <div key={m.id} className="flex items-start gap-2 text-sm">
                          <Badge variant="outline" className="font-mono text-xs shrink-0">
                            {m.memory_type}
                          </Badge>
                          <Link
                            href={`/memories/${m.id}`}
                            onClick={() => onOpenChange(false)}
                            className="text-muted-foreground hover:text-foreground truncate"
                          >
                            {m.summary || `Memory #${m.id}`}
                          </Link>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Actions */}
              {!isTerminal && (
                <>
                  <Separator />
                  <div className="flex gap-2">
                    {!detail.assignee && (
                      <Button
                        onClick={handleClaim}
                        disabled={acting}
                        size="sm"
                        variant="outline"
                        className="flex-1"
                      >
                        <User className="mr-1 h-3.5 w-3.5" />
                        Claim
                      </Button>
                    )}
                    <Button
                      onClick={handleComplete}
                      disabled={acting}
                      size="sm"
                      className="flex-1"
                    >
                      <CheckCircle className="mr-1 h-3.5 w-3.5" />
                      Complete
                    </Button>
                    <Button
                      onClick={handleCancel}
                      disabled={acting}
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                    >
                      <XCircle className="mr-1 h-3.5 w-3.5" />
                      Cancel
                    </Button>
                  </div>
                </>
              )}

              {/* Metadata */}
              {detail.metadata && Object.keys(detail.metadata).length > 0 && (
                <>
                  <Separator />
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                      Metadata
                    </summary>
                    <pre className="mt-2 rounded bg-muted p-2 overflow-x-auto font-mono text-xs">
                      {JSON.stringify(detail.metadata, null, 2)}
                    </pre>
                  </details>
                </>
              )}

              {/* Footer info */}
              <Separator />
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>ID: {detail.id} ({detail.short_id})</p>
                <p>Created: {formatDateTime(detail.created_at)}</p>
                {detail.updated_at && <p>Updated: {formatDateTime(detail.updated_at)}</p>}
                {detail.completed_at && <p>Completed: {formatDateTime(detail.completed_at)}</p>}
                {detail.cancelled_at && <p>Cancelled: {formatDateTime(detail.cancelled_at)}</p>}
                {detail.session_name && <p>Session: {detail.session_name}</p>}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function SectionHeader({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
      {icon}
      {children}
    </h3>
  );
}
