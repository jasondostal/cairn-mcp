"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, type WorkItemDetail, type WorkItemActivity, type WorkItemStatus } from "@/lib/api";
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
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { StatusDot, StatusText, PriorityLabel } from "./status-dot";
import { RiskTierBadge } from "./risk-tier-badge";
import {
  CheckCircle,
  Clock,
  GitBranch,
  Hand,
  Link2,
  Lock,
  Shield,
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
  const [activities, setActivities] = useState<WorkItemActivity[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [gateResponse, setGateResponse] = useState("");

  const fetchDetail = useCallback(() => {
    if (!itemId) return;
    setLoading(true);
    api.workItem(itemId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [itemId]);

  const fetchActivities = useCallback(() => {
    if (!itemId) return;
    setActivitiesLoading(true);
    api.workItemActivity(itemId, { limit: "30" })
      .then((r) => setActivities(r.activities))
      .catch(() => setActivities([]))
      .finally(() => setActivitiesLoading(false));
  }, [itemId]);

  useEffect(() => {
    if (!itemId || !open) return;
    fetchDetail();
    fetchActivities();
  }, [itemId, open, fetchDetail, fetchActivities]);

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
      const updated = await api.workItem(detail.id);
      setDetail(updated);
      fetchActivities();
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

  async function handleResolveGate() {
    if (!detail) return;
    setActing(true);
    try {
      const response: Record<string, unknown> = { text: gateResponse };
      await api.workItemResolveGate(detail.id, response, "user");
      setGateResponse("");
      const updated = await api.workItem(detail.id);
      setDetail(updated);
      fetchActivities();
      onAction?.();
    } catch { /* silent */ }
    finally { setActing(false); }
  }

  function navigateTo(id: number) {
    onNavigate?.(id);
  }

  const isTerminal = detail?.status === "done" || detail?.status === "cancelled";
  const hasUnresolvedGate = detail?.gate_type && !detail?.gate_resolved_at;
  const constraints = detail?.constraints ?? {};
  const hasConstraints = Object.keys(constraints).length > 0;

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
                <PriorityLabel priority={detail.priority} />
                <RiskTierBadge tier={detail.risk_tier} />
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

              {/* Gate — Needs Your Input (prominent if unresolved) */}
              {hasUnresolvedGate && (
                <div className="rounded-md border border-[oklch(0.627_0.265_304)]/30 bg-[oklch(0.627_0.265_304)]/5 p-3 space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-[oklch(0.627_0.265_304)]">
                    <Hand className="h-4 w-4" />
                    Needs Your Input
                  </div>
                  {typeof detail.gate_data?.question === "string" && (
                    <p className="text-sm">{detail.gate_data.question}</p>
                  )}
                  {typeof detail.gate_data?.context === "string" && (
                    <p className="text-xs text-muted-foreground">{detail.gate_data.context}</p>
                  )}
                  {Array.isArray(detail.gate_data?.options) && (
                    <div className="flex flex-wrap gap-1.5">
                      {(detail.gate_data.options as string[]).map((opt) => (
                        <Button
                          key={opt}
                          size="xs"
                          variant="outline"
                          onClick={() => {
                            setGateResponse(opt);
                          }}
                          className={gateResponse === opt ? "border-primary" : ""}
                        >
                          {opt}
                        </Button>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Input
                      value={gateResponse}
                      onChange={(e) => setGateResponse(e.target.value)}
                      placeholder="Your response…"
                      className="h-8 text-sm"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && gateResponse.trim()) handleResolveGate();
                      }}
                    />
                    <Button
                      size="sm"
                      onClick={handleResolveGate}
                      disabled={acting || !gateResponse.trim()}
                    >
                      Resolve
                    </Button>
                  </div>
                </div>
              )}

              {/* Resolved gate info */}
              {detail.gate_type && detail.gate_resolved_at && (
                <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <CheckCircle className="h-3 w-3 text-[oklch(0.696_0.17_162)]" />
                  Gate ({detail.gate_type}) resolved {formatDateTime(detail.gate_resolved_at)}
                  {typeof detail.gate_response?.text === "string" && (
                    <span className="font-mono">— {detail.gate_response.text}</span>
                  )}
                </div>
              )}

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

              {/* Assignee + Agent State */}
              {(detail.assignee || detail.agent_state) && (
                <div className="flex items-center gap-3 text-sm">
                  {detail.assignee && (
                    <div className="flex items-center gap-1.5">
                      <User className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-mono text-muted-foreground">@{detail.assignee}</span>
                    </div>
                  )}
                  {detail.agent_state && (
                    <Badge variant="outline" className="font-mono text-xs">
                      {detail.agent_state}
                    </Badge>
                  )}
                  {detail.last_heartbeat && (
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDateTime(detail.last_heartbeat)}
                    </span>
                  )}
                </div>
              )}

              {/* Constraints */}
              {hasConstraints && (
                <>
                  <Separator />
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground flex items-center gap-1">
                      <Shield className="h-3 w-3" />
                      Constraints ({Object.keys(constraints).length})
                    </summary>
                    <div className="mt-2 space-y-1">
                      {Object.entries(constraints).map(([key, val]) => (
                        <div key={key} className="flex items-baseline gap-2 font-mono">
                          <span className="text-muted-foreground">{key}:</span>
                          <span>{String(val)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                </>
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

              {/* Activity Feed */}
              <Separator />
              <details open={activities.length > 0 && activities.length <= 10}>
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Activity ({activities.length})
                </summary>
                <div className="mt-2 space-y-1.5 max-h-64 overflow-y-auto">
                  {activitiesLoading && (
                    <p className="text-xs text-muted-foreground">Loading...</p>
                  )}
                  {activities.map((a) => (
                    <div key={a.id} className="flex items-baseline gap-2 text-xs">
                      <span className="text-muted-foreground/60 font-mono shrink-0 w-32 text-right">
                        {formatDateTime(a.created_at)}
                      </span>
                      <ActivityIcon type={a.activity_type} />
                      <span className="text-muted-foreground truncate">
                        {a.content || a.activity_type}
                      </span>
                      {a.actor && (
                        <span className="font-mono text-muted-foreground/60 shrink-0">
                          {a.actor}
                        </span>
                      )}
                    </div>
                  ))}
                  {!activitiesLoading && activities.length === 0 && (
                    <p className="text-xs text-muted-foreground">No activity yet.</p>
                  )}
                </div>
              </details>

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

const activityIcons: Record<string, string> = {
  created: "+"  ,
  status_change: "~",
  claim: "@",
  gate_set: "!",
  gate_resolved: "v",
  heartbeat: ".",
  checkpoint: "#",
  note: "*",
};

function ActivityIcon({ type }: { type: string }) {
  const icon = activityIcons[type] ?? "·";
  return (
    <span className="font-mono text-muted-foreground/60 shrink-0 w-3 text-center">{icon}</span>
  );
}
