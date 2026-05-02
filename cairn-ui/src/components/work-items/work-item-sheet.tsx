"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type WorkItem, type WorkItemDetail, type WorkItemActivity, type WorkItemStatus, type WorkspaceBackendInfo, type Deliverable } from "@/lib/api";
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
import { SingleSelect } from "@/components/ui/single-select";
import { Separator } from "@/components/ui/separator";
import { StatusDot, StatusText, PriorityLabel } from "./status-dot";
import { RiskTierBadge } from "./risk-tier-badge";
import { ProjectPill } from "@/components/project-pill";
import { DispatchDialog } from "./dispatch-dialog";
import {
  Bot,
  CheckCircle,
  Clock,
  FileCheck,
  GitBranch,
  Hand,
  Link2,
  Lock,
  MessageSquare,
  Pencil,
  Plus,
  Radio,
  RotateCcw,
  Shield,
  ThumbsDown,
  ThumbsUp,
  User,
  X,
  XCircle,
} from "lucide-react";

const STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "ready", label: "Ready" },
  { value: "in_progress", label: "In Progress" },
  { value: "blocked", label: "Blocked" },
  { value: "done", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
];

const PRIORITY_OPTIONS = Array.from({ length: 11 }, (_, i) => ({
  value: String(i),
  label: `P${i}${i === 0 ? " (none)" : i <= 2 ? " (low)" : i <= 5 ? "" : i <= 8 ? " (high)" : " (critical)"}`,
}));

/** Click-to-edit text field. Shows static text, switches to input on click. */
function EditableText({
  value,
  onSave,
  multiline = false,
  disabled = false,
  className = "",
  placeholder = "Click to edit…",
}: {
  value: string;
  onSave: (v: string) => Promise<void>;
  multiline?: boolean;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  async function save() {
    const trimmed = draft.trim();
    if (trimmed === value) { setEditing(false); return; }
    setSaving(true);
    try {
      await onSave(trimmed);
      setEditing(false);
    } catch { setDraft(value); }
    finally { setSaving(false); }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { setDraft(value); setEditing(false); }
    if (e.key === "Enter" && !multiline) { e.preventDefault(); save(); }
    if (e.key === "Enter" && multiline && (e.metaKey || e.ctrlKey)) { e.preventDefault(); save(); }
  }

  if (disabled || !editing) {
    return (
      <div
        className={`group cursor-pointer ${disabled ? "cursor-default" : ""} ${className}`}
        onClick={() => !disabled && setEditing(true)}
      >
        <span className={value ? "" : "text-muted-foreground italic"}>
          {value || placeholder}
        </span>
        {!disabled && (
          <Pencil className="h-3 w-3 ml-1.5 inline opacity-0 group-hover:opacity-40 transition-opacity" />
        )}
      </div>
    );
  }

  const inputClass = "w-full rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  if (multiline) {
    return (
      <textarea
        ref={ref as React.RefObject<HTMLTextAreaElement>}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={handleKeyDown}
        disabled={saving}
        className={`${inputClass} min-h-[80px] resize-y ${className}`}
        placeholder={placeholder}
      />
    );
  }

  return (
    <input
      ref={ref as React.RefObject<HTMLInputElement>}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={save}
      onKeyDown={handleKeyDown}
      disabled={saving}
      className={`${inputClass} h-8 ${className}`}
      placeholder={placeholder}
    />
  );
}

interface WorkItemSheetProps {
  itemId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAction?: () => void;
  onNavigate?: (id: number) => void;
  backends?: WorkspaceBackendInfo[];
}

export function WorkItemSheet({
  itemId,
  open,
  onOpenChange,
  onAction,
  onNavigate,
  backends,
}: WorkItemSheetProps) {
  const [detail, setDetail] = useState<WorkItemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [activities, setActivities] = useState<WorkItemActivity[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [gateResponse, setGateResponse] = useState("");
  const [editingParent, setEditingParent] = useState(false);
  const [parentOptions, setParentOptions] = useState<WorkItem[]>([]);
  const [parentSaving, setParentSaving] = useState(false);
  const [deliverable, setDeliverable] = useState<Deliverable | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewActing, setReviewActing] = useState(false);

  /** Generic field update — patches via API, refreshes detail + activity. */
  async function updateField(field: string, value: unknown) {
    if (!detail) return;
    await api.workItemUpdate(detail.id, { [field]: value });
    const updated = await api.workItem(detail.id);
    setDetail(updated);
    fetchActivities();
    onAction?.();
  }

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

  const fetchDeliverable = useCallback(() => {
    if (!itemId) return;
    api.deliverable(itemId)
      .then((d) => setDeliverable(d?.id ? d : null))
      .catch(() => setDeliverable(null));
  }, [itemId]);

  useEffect(() => {
    if (!itemId || !open) return;
    fetchDetail();
    fetchActivities();
    fetchDeliverable();
  }, [itemId, open, fetchDetail, fetchActivities, fetchDeliverable]);

  // Auto-refresh while agent is working (in_progress or has recent heartbeat)
  useEffect(() => {
    if (!open || !detail) return;
    const isActive = detail.status === "in_progress" || (
      detail.agent_state === "working" && detail.last_heartbeat
      && (Date.now() - new Date(detail.last_heartbeat).getTime()) < 120_000
    );
    if (!isActive) return;

    const interval = setInterval(() => {
      fetchDetail();
      fetchActivities();
      fetchDeliverable();
    }, 5_000); // 5s refresh while agent is active
    return () => clearInterval(interval);
  }, [open, detail?.status, detail?.agent_state, detail?.last_heartbeat, fetchDetail, fetchActivities, fetchDeliverable]);

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

  async function handleReview(action: "approve" | "revise" | "reject") {
    if (!detail || !deliverable) return;
    setReviewActing(true);
    try {
      await api.reviewDeliverable(detail.id, {
        action,
        reviewer: "user",
        notes: reviewNotes || undefined,
      });
      setReviewNotes("");
      fetchDeliverable();
      fetchActivities();
      onAction?.();
    } catch { /* silent */ }
    finally { setReviewActing(false); }
  }

  function navigateTo(id: number) {
    onNavigate?.(id);
  }

  async function startEditParent() {
    if (!detail) return;
    setEditingParent(true);
    try {
      const result = await api.workItems({ project: detail.project, limit: "100" });
      // Filter out self and own children
      setParentOptions(result.items.filter((wi) => wi.id !== detail.id));
    } catch {
      setParentOptions([]);
    }
  }

  async function handleParentChange(newParentId: string) {
    if (!detail) return;
    setParentSaving(true);
    try {
      const pid = newParentId === "" ? null : Number(newParentId);
      await api.workItemUpdate(detail.id, { parent_id: pid });
      fetchDetail();
      onAction?.();
      setEditingParent(false);
    } catch { /* silent */ }
    finally { setParentSaving(false); }
  }

  const isTerminal = detail?.status === "done" || detail?.status === "cancelled";
  const hasUnresolvedGate = detail?.gate_type && !detail?.gate_resolved_at;
  const constraints = detail?.constraints ?? {};
  const hasConstraints = Object.keys(constraints).length > 0;
  const isReviewable = deliverable && (deliverable.status === "draft" || deliverable.status === "pending_review");
  const isReviewed = deliverable && (deliverable.status === "approved" || deliverable.status === "revised" || deliverable.status === "rejected");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-xl lg:max-w-2xl">
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
                {isTerminal ? (
                  <StatusText status={detail.status} />
                ) : (
                  <SingleSelect
                    options={STATUS_OPTIONS}
                    value={detail.status}
                    onValueChange={(v) => { if (v) updateField("status", v); }}
                    className="h-6 min-w-0 text-xs"
                  />
                )}
                <Badge variant="outline" className="font-mono text-xs">
                  {detail.item_type}
                </Badge>
                <Link href={`/projects/${encodeURIComponent(detail.project)}`} onClick={() => onOpenChange(false)}>
                  <ProjectPill name={detail.project} />
                </Link>
                {isTerminal ? (
                  <PriorityLabel priority={detail.priority} />
                ) : (
                  <SingleSelect
                    options={PRIORITY_OPTIONS}
                    value={String(detail.priority)}
                    onValueChange={(v) => { if (v) updateField("priority", Number(v)); }}
                    className="h-6 min-w-0 text-xs"
                  />
                )}
                <RiskTierBadge tier={detail.risk_tier} />
              </div>
              <SheetTitle className="font-mono text-lg">
                {detail.display_id}
              </SheetTitle>
              <EditableText
                value={detail.title}
                onSave={(v) => updateField("title", v)}
                disabled={isTerminal}
                className="text-sm text-foreground"
                placeholder="Untitled"
              />
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              <Separator />

              {/* Gate — Needs Your Input (prominent if unresolved) */}
              {hasUnresolvedGate && (
                <div className="rounded-md border border-status-gate/30 bg-status-gate/5 p-3 space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-status-gate">
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
                  <CheckCircle className="h-3 w-3 text-status-done" />
                  Gate ({detail.gate_type}) resolved {formatDateTime(detail.gate_resolved_at)}
                  {typeof detail.gate_response?.text === "string" && (
                    <span className="font-mono">— {detail.gate_response.text}</span>
                  )}
                </div>
              )}

              {/* Description */}
              {(detail.description || !isTerminal) && (
                <div>
                  <SectionHeader>Description</SectionHeader>
                  <EditableText
                    value={detail.description || ""}
                    onSave={(v) => updateField("description", v || null)}
                    multiline
                    disabled={isTerminal}
                    className="whitespace-pre-wrap text-sm leading-relaxed"
                    placeholder="Add a description…"
                  />
                </div>
              )}

              {/* Acceptance Criteria */}
              {(detail.acceptance_criteria || !isTerminal) && (
                <div>
                  <SectionHeader>Acceptance Criteria</SectionHeader>
                  <EditableText
                    value={detail.acceptance_criteria || ""}
                    onSave={(v) => updateField("acceptance_criteria", v || null)}
                    multiline
                    disabled={isTerminal}
                    className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground"
                    placeholder="Add acceptance criteria…"
                  />
                </div>
              )}

              {/* Assignee + Agent State */}
              <div className="flex items-center gap-3 text-sm">
                <div className="flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5 text-muted-foreground" />
                  {isTerminal ? (
                    <span className="font-mono text-muted-foreground">
                      {detail.assignee ? `@${detail.assignee}` : "Unassigned"}
                    </span>
                  ) : (
                    <EditableText
                      value={detail.assignee || ""}
                      onSave={(v) => updateField("assignee", v || null)}
                      className="font-mono text-muted-foreground"
                      placeholder="Unassigned"
                    />
                  )}
                </div>
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
              <>
                <Separator />
                <div>
                  <SectionHeader icon={<GitBranch className="h-3 w-3" />}>
                    Hierarchy
                  </SectionHeader>
                  {editingParent ? (
                    <div className="mb-2 flex items-center gap-2">
                      <SingleSelect
                        options={[
                          { value: "", label: "No parent" },
                          ...parentOptions.map((wi) => ({
                            value: String(wi.id),
                            label: `${wi.display_id} ${wi.title}`,
                          })),
                        ]}
                        value={detail.parent ? String(detail.parent.id) : ""}
                        onValueChange={handleParentChange}
                        placeholder="Select parent…"
                        className="flex-1 h-7 text-xs"
                        disabled={parentSaving}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => setEditingParent(false)}
                        aria-label="Cancel parent edit"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="mb-2 flex items-center gap-1">
                      {detail.parent ? (
                        <>
                          <span className="text-xs text-muted-foreground mr-1">Parent:</span>
                          <button
                            onClick={() => navigateTo(detail.parent!.id)}
                            className="text-sm text-primary hover:underline font-mono"
                          >
                            {detail.parent.display_id}
                          </button>
                          <span className="text-sm text-muted-foreground ml-1 truncate">{detail.parent.title}</span>
                          {!isTerminal && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 ml-auto shrink-0"
                              onClick={startEditParent}
                              title="Change parent"
                              aria-label="Change parent"
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                          )}
                        </>
                      ) : (
                        <>
                          <span className="text-xs text-muted-foreground">No parent</span>
                          {!isTerminal && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-5 px-1.5 ml-auto text-xs gap-1"
                              onClick={startEditParent}
                            >
                              <Plus className="h-3 w-3" />
                              Set parent
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  {detail.children_count > 0 && (
                    <div className="text-xs text-muted-foreground">
                      {detail.children_count} child{detail.children_count !== 1 ? "ren" : ""}
                    </div>
                  )}
                </div>
              </>

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
                                {b.display_id}
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
                                {b.display_id}
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

              {/* Deliverable */}
              {deliverable && (
                <>
                  <Separator />
                  <div>
                    <SectionHeader icon={<FileCheck className="h-3 w-3" />}>
                      Deliverable v{deliverable.version}
                      <Badge
                        variant="outline"
                        className={`ml-2 text-[10px] ${
                          deliverable.status === "approved"
                            ? "border-status-done text-status-done"
                            : deliverable.status === "revised"
                              ? "border-status-wip text-status-wip"
                              : deliverable.status === "rejected"
                                ? "border-destructive text-destructive"
                                : deliverable.status === "pending_review"
                                  ? "border-status-gate text-status-gate"
                                  : ""
                        }`}
                      >
                        {deliverable.status.replace("_", " ")}
                      </Badge>
                    </SectionHeader>

                    {/* Summary */}
                    {deliverable.summary && (
                      <p className="text-sm leading-relaxed mb-3">{deliverable.summary}</p>
                    )}

                    {/* Changes */}
                    {deliverable.changes.length > 0 && (
                      <div className="mb-2">
                        <span className="text-xs text-muted-foreground block mb-1">Changes:</span>
                        <ul className="space-y-0.5 text-sm">
                          {deliverable.changes.map((c, i) => (
                            <li key={i} className="flex items-start gap-2">
                              <span className="text-muted-foreground/60 shrink-0">-</span>
                              <span>{c.description}</span>
                              {c.type && (
                                <Badge variant="outline" className="text-[10px] shrink-0">{c.type}</Badge>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Decisions */}
                    {deliverable.decisions.length > 0 && (
                      <div className="mb-2">
                        <span className="text-xs text-muted-foreground block mb-1">Decisions:</span>
                        <ul className="space-y-1 text-sm">
                          {deliverable.decisions.map((d, i) => (
                            <li key={i}>
                              <span className="font-medium">{d.decision}</span>
                              {d.rationale && (
                                <span className="text-muted-foreground text-xs ml-1">— {d.rationale}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Open items */}
                    {deliverable.open_items.length > 0 && (
                      <div className="mb-2">
                        <span className="text-xs text-muted-foreground block mb-1">Open items:</span>
                        <ul className="space-y-0.5 text-sm">
                          {deliverable.open_items.map((o, i) => (
                            <li key={i} className="flex items-center gap-2">
                              <span className="text-muted-foreground/60 shrink-0">-</span>
                              <span>{o.description}</span>
                              {o.priority && (
                                <Badge variant="outline" className="text-[10px] shrink-0">{o.priority}</Badge>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Metrics */}
                    {deliverable.metrics && Object.keys(deliverable.metrics).length > 0 && (
                      <div className="flex gap-3 text-xs text-muted-foreground mb-2">
                        {Object.entries(deliverable.metrics).map(([k, v]) => (
                          <span key={k} className="font-mono">{k}: {String(v)}</span>
                        ))}
                      </div>
                    )}

                    {/* Reviewed info */}
                    {isReviewed && deliverable.reviewed_by && (
                      <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-2">
                        <User className="h-3 w-3" />
                        Reviewed by {deliverable.reviewed_by}
                        {deliverable.reviewed_at && <span>— {formatDateTime(deliverable.reviewed_at)}</span>}
                      </div>
                    )}
                    {isReviewed && deliverable.reviewer_notes && (
                      <div className="text-sm bg-muted rounded p-2 mb-2">
                        <span className="text-xs text-muted-foreground block mb-0.5">
                          <MessageSquare className="h-3 w-3 inline mr-1" />
                          Review notes:
                        </span>
                        {deliverable.reviewer_notes}
                      </div>
                    )}

                    {/* Review actions */}
                    {isReviewable && (
                      <div className="mt-3 space-y-2">
                        <textarea
                          value={reviewNotes}
                          onChange={(e) => setReviewNotes(e.target.value)}
                          placeholder="Review notes (optional for approve, recommended for revise/reject)…"
                          className="w-full h-16 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                        />
                        <div className="flex gap-2">
                          <Button
                            onClick={() => handleReview("approve")}
                            disabled={reviewActing}
                            size="sm"
                            className="flex-1 bg-status-done hover:bg-status-done/90 text-white"
                          >
                            <ThumbsUp className="mr-1 h-3.5 w-3.5" />
                            Approve
                          </Button>
                          <Button
                            onClick={() => handleReview("revise")}
                            disabled={reviewActing}
                            size="sm"
                            variant="outline"
                            className="flex-1 border-status-wip text-status-wip hover:bg-status-wip/10"
                          >
                            <RotateCcw className="mr-1 h-3.5 w-3.5" />
                            Revise
                          </Button>
                          <Button
                            onClick={() => handleReview("reject")}
                            disabled={reviewActing}
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                          >
                            <ThumbsDown className="mr-1 h-3.5 w-3.5" />
                            Reject
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Actions */}
              {!isTerminal && (
                <>
                  <Separator />
                  <div className="flex gap-2">
                    {backends && backends.length > 0 && detail.status !== "in_progress" && (
                      <>
                        <Button
                          onClick={() => setDispatchOpen(true)}
                          disabled={acting}
                          size="sm"
                          variant="outline"
                          className="flex-1"
                        >
                          <Bot className="mr-1 h-3.5 w-3.5" />
                          Dispatch
                        </Button>
                        <DispatchDialog
                          open={dispatchOpen}
                          onOpenChange={setDispatchOpen}
                          item={detail}
                          backends={backends}
                          onDispatched={() => {
                            onAction?.();
                            onOpenChange(false);
                          }}
                        />
                      </>
                    )}
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

              {/* Linked Sessions */}
              {detail.linked_sessions && detail.linked_sessions.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <SectionHeader icon={<Radio className="h-3 w-3" />}>
                      Sessions ({detail.linked_sessions.length})
                    </SectionHeader>
                    <div className="space-y-1.5">
                      {detail.linked_sessions.map((ls) => (
                        <div key={ls.session_name} className="flex items-center gap-2 text-sm">
                          {ls.is_active ? (
                            <span className="relative flex h-2 w-2 shrink-0">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                            </span>
                          ) : (
                            <span className="h-2 w-2 rounded-full bg-muted-foreground/30 shrink-0" />
                          )}
                          <span className="font-mono text-xs truncate">
                            {ls.session_name}
                          </span>
                          <Badge variant="outline" className="text-[10px] px-1 py-0 shrink-0">
                            {ls.role}
                          </Badge>
                          {ls.touch_count > 1 && (
                            <span className="text-xs text-muted-foreground/60 shrink-0">
                              {ls.touch_count}x
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
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
                <p>ID: {detail.id} ({detail.display_id})</p>
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
  created: "+",
  status_change: "~",
  claim: "@",
  gate_set: "!",
  gate_resolved: "v",
  heartbeat: ".",
  checkpoint: "#",
  note: "*",
  review: "R",
  deliverable: "D",
};

function ActivityIcon({ type }: { type: string }) {
  const icon = activityIcons[type] ?? "·";
  return (
    <span className="font-mono text-muted-foreground/60 shrink-0 w-3 text-center">{icon}</span>
  );
}

