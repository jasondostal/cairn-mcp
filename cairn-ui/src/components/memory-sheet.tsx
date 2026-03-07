"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Memory, type UpdateMemoryRequest } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { relationClasses } from "@/lib/colors";
import { StatusDot } from "@/components/work-items/status-dot";
import {
  Tag,
  FileText,
  Network,
  ArrowRight,
  ArrowLeft,
  Link2,
  Pencil,
  Save,
  X,
  Trash2,
  RotateCcw,
} from "lucide-react";

const VALID_MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
];

const MEMORY_TYPE_OPTIONS = VALID_MEMORY_TYPES.map((t) => ({
  value: t,
  label: t,
}));

interface MemorySheetProps {
  memoryId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MemorySheet({ memoryId, open, onOpenChange }: MemorySheetProps) {
  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkedWorkItems, setLinkedWorkItems] = useState<Array<{ id: number; display_id: string; title: string; status: string; item_type: string; project: string }>>([]);

  // Edit mode state
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<Partial<UpdateMemoryRequest>>({});

  // Inactivate dialog state
  const [inactivateReason, setInactivateReason] = useState("");

  // Draft persistence — survive accidental refresh
  const draftKey = memoryId ? `cairn-memory-draft-${memoryId}` : null;

  const saveDraft = (data: Partial<UpdateMemoryRequest>) => {
    if (draftKey) sessionStorage.setItem(draftKey, JSON.stringify(data));
  };

  const loadDraft = useCallback((): Partial<UpdateMemoryRequest> | null => {
    if (!draftKey) return null;
    try {
      const raw = sessionStorage.getItem(draftKey);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }, [draftKey]);

  const clearDraft = () => {
    if (draftKey) sessionStorage.removeItem(draftKey);
  };

  const fetchMemory = (id: number) => {
    setLoading(true);
    setError(null);
    api
      .memory(id)
      .then(setMemory)
      .catch((err) => setError(err?.message || "Failed to load memory"))
      .finally(() => setLoading(false));
    api
      .memoryWorkItems(id)
      .then((r) => setLinkedWorkItems(r.work_items))
      .catch((err) => { console.error("Linked work-items fetch failed", err); setLinkedWorkItems([]); });
  };

  useEffect(() => {
    if (!memoryId || !open) return;
    // Check for a saved draft before resetting edit state
    const draft = loadDraft();
    if (draft) {
      setFormData(draft);
      setEditing(true);
    } else {
      setEditing(false);
    }
    fetchMemory(memoryId);
  }, [memoryId, open, loadDraft]);

  const startEditing = () => {
    if (!memory) return;
    const initial = {
      content: memory.content,
      memory_type: memory.memory_type,
      importance: memory.importance,
      tags: memory.tags,
    };
    setFormData(initial);
    saveDraft(initial);
    setEditing(true);
  };

  const updateFormData = (updater: (prev: Partial<UpdateMemoryRequest>) => Partial<UpdateMemoryRequest>) => {
    setFormData((prev) => {
      const next = updater(prev);
      saveDraft(next);
      return next;
    });
  };

  const cancelEditing = () => {
    clearDraft();
    setFormData({});
    setEditing(false);
  };

  const handleSave = async () => {
    if (!memoryId) return;
    setSaving(true);
    try {
      await api.updateMemory(memoryId, formData);
      clearDraft();
      fetchMemory(memoryId);
      setEditing(false);
    } catch (err) {
      setError((err as Error)?.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleInactivate = async () => {
    if (!memoryId) return;
    setSaving(true);
    try {
      await api.inactivateMemory(memoryId, inactivateReason || "No reason provided");
      setInactivateReason("");
      fetchMemory(memoryId);
    } catch (err) {
      setError((err as Error)?.message || "Failed to inactivate");
    } finally {
      setSaving(false);
    }
  };

  const handleReactivate = async () => {
    if (!memoryId) return;
    setSaving(true);
    try {
      await api.reactivateMemory(memoryId);
      fetchMemory(memoryId);
    } catch (err) {
      setError((err as Error)?.message || "Failed to reactivate");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-xl lg:max-w-2xl">
        {loading && (
          <SheetHeader>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-32" />
            <div className="space-y-2 pt-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          </SheetHeader>
        )}

        {error && (
          <SheetHeader>
            <SheetTitle>Error</SheetTitle>
            <SheetDescription>{error}</SheetDescription>
          </SheetHeader>
        )}

        {!loading && !error && memory && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2">
                <MemoryTypeBadge type={memory.memory_type} />
                <span className="text-xs text-muted-foreground">
                  #{memory.id}
                </span>
                {!editing && (
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={startEditing} title="Edit">
                    <Pencil className="h-3 w-3" />
                  </Button>
                )}
              </div>
              <SheetTitle className="text-base">
                {memory.summary || "Memory #" + memory.id}
              </SheetTitle>
              <SheetDescription>
                <Link href={`/projects/${encodeURIComponent(memory.project)}`} onClick={() => onOpenChange(false)} className="text-primary hover:underline">{memory.project}</Link> &middot;{" "}
                {formatDateTime(memory.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              {/* Edit mode: Save / Cancel bar */}
              {editing && (
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={handleSave} disabled={saving}>
                    <Save className="h-3.5 w-3.5 mr-1" />
                    {saving ? "Saving..." : "Save"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={cancelEditing} disabled={saving}>
                    <X className="h-3.5 w-3.5 mr-1" />
                    Cancel
                  </Button>
                </div>
              )}

              {/* Stats / Editable fields */}
              <div className="flex items-center gap-4 text-sm">
                {editing ? (
                  <div className="flex items-center gap-2">
                    <label htmlFor="memory-importance" className="text-xs text-muted-foreground">Importance:</label>
                    <Input
                      id="memory-importance"
                      type="number"
                      step="0.1"
                      min="0"
                      max="1"
                      value={formData.importance ?? 0.5}
                      onChange={(e) => updateFormData((f) => ({ ...f, importance: parseFloat(e.target.value) || 0 }))}
                      className="h-7 w-20 text-xs"
                    />
                  </div>
                ) : (
                  <ImportanceBadge importance={memory.importance} />
                )}
                {!memory.is_active && (
                  <Badge variant="destructive" className="text-xs">
                    Inactive
                  </Badge>
                )}
              </div>

              {/* Memory type (editable) */}
              {editing && (
                <div className="flex items-center gap-2">
                  <label htmlFor="memory-type" className="text-xs text-muted-foreground">Type:</label>
                  <SingleSelect
                    options={MEMORY_TYPE_OPTIONS}
                    value={formData.memory_type || memory.memory_type}
                    onValueChange={(v) => updateFormData((f) => ({ ...f, memory_type: v }))}
                  />
                </div>
              )}

              <Separator />

              {/* Content */}
              <div>
                <label htmlFor="memory-content" className="mb-2 block text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Content
                </label>
                {editing ? (
                  <textarea
                    id="memory-content"
                    value={formData.content ?? ""}
                    onChange={(e) => updateFormData((f) => ({ ...f, content: e.target.value }))}
                    className="w-full min-h-[200px] rounded-md border bg-background px-3 py-2 text-sm font-mono leading-relaxed resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                ) : (
                  <p className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                    {memory.content}
                  </p>
                )}
              </div>

              {/* Tags */}
              {(editing || memory.tags.length > 0 || memory.auto_tags.length > 0) && (
                <>
                  <Separator />
                  <div>
                    <label htmlFor="memory-tags" className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Tag className="h-3 w-3" /> Tags
                    </label>
                    {editing ? (
                      <div className="space-y-2">
                        <Input
                          id="memory-tags"
                          value={(formData.tags ?? []).join(", ")}
                          onChange={(e) => {
                            const tags = e.target.value.split(",").map((t) => t.trim()).filter(Boolean);
                            updateFormData((f) => ({ ...f, tags }));
                          }}
                          placeholder="tag1, tag2, tag3"
                          className="h-7 text-xs"
                        />
                        {memory.auto_tags.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            <span className="text-[10px] text-muted-foreground">Auto:</span>
                            {memory.auto_tags.map((t) => (
                              <Badge key={t} variant="outline" className="text-xs">
                                {t}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {memory.tags.map((t) => (
                          <Badge key={t} variant="secondary" className="text-xs">
                            {t}
                          </Badge>
                        ))}
                        {memory.auto_tags.map((t) => (
                          <Badge key={t} variant="outline" className="text-xs">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Related Files */}
              {memory.related_files?.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <FileText className="h-3 w-3" /> Related Files
                    </h3>
                    <div className="space-y-1">
                      {memory.related_files.map((f) => (
                        <p key={f} className="font-mono text-xs text-muted-foreground">
                          {f}
                        </p>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Relations */}
              {memory.relations && memory.relations.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Network className="h-3 w-3" /> Relations
                    </h3>
                    <div className="space-y-2">
                      {memory.relations.map((rel, i) => (
                        <div
                          key={`${rel.id}-${rel.relation}-${i}`}
                          className="flex items-start gap-2 text-sm group cursor-pointer hover:bg-accent/50 rounded-md p-1.5 -mx-1.5 transition-colors"
                          onClick={() => {
                            onOpenChange(false);
                            setTimeout(() => {
                              window.location.href = `/memories/${rel.id}`;
                            }, 150);
                          }}
                        >
                          {rel.direction === "outgoing" ? (
                            <ArrowRight className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                          ) : (
                            <ArrowLeft className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className={`text-xs font-medium ${relationClasses(rel.relation).text}`}>
                                {rel.relation.replace("_", " ")}
                              </span>
                              <MemoryTypeBadge type={rel.memory_type} />
                              <span className="text-xs text-muted-foreground">
                                #{rel.id}
                              </span>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                              {rel.summary}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Cluster */}
              {memory.cluster && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Network className="h-3 w-3" /> Cluster
                    </h3>
                    <p className="text-sm">
                      <Link href="/clusters" onClick={() => onOpenChange(false)} className="text-primary hover:underline">{memory.cluster.label}</Link>
                      <span className="ml-2 text-xs text-muted-foreground">
                        ({memory.cluster.size} members)
                      </span>
                    </p>
                  </div>
                </>
              )}

              {/* Linked Work Items */}
              {linkedWorkItems.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Link2 className="h-3 w-3" /> Linked Work Items
                    </h3>
                    <div className="space-y-1.5">
                      {linkedWorkItems.map((wi) => (
                        <Link
                          key={wi.id}
                          href={`/work-items?id=${wi.id}`}
                          onClick={() => onOpenChange(false)}
                          className="flex items-center gap-2 text-sm hover:bg-accent/50 rounded-md p-1 -mx-1 transition-colors"
                        >
                          <StatusDot status={wi.status as "open" | "ready" | "in_progress" | "blocked" | "done" | "cancelled"} />
                          <span className="font-mono text-xs text-muted-foreground">{wi.display_id}</span>
                          <span className="truncate text-xs">{wi.title}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Metadata */}
              <Separator />
              <div className="space-y-1 text-xs text-muted-foreground">
                {memory.session_name && (
                  <p>Session: <Link href={`/sessions?selected=${encodeURIComponent(memory.session_name)}`} onClick={() => onOpenChange(false)} className="text-primary hover:underline">{memory.session_name}</Link></p>
                )}
                <p>Created: {formatDateTime(memory.created_at)}</p>
                <p>Updated: {formatDateTime(memory.updated_at)}</p>
                {memory.inactive_reason && (
                  <p>Inactive reason: {memory.inactive_reason}</p>
                )}
              </div>

              {/* Action buttons */}
              {!editing && (
                <>
                  <Separator />
                  <div className="flex items-center gap-2">
                    {memory.is_active ? (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="destructive" size="sm">
                            <Trash2 className="h-3.5 w-3.5 mr-1" />
                            Inactivate
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Inactivate Memory #{memory.id}</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will soft-delete the memory. It can be reactivated later.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <div className="space-y-1">
                            <label htmlFor="inactivate-reason" className="text-xs font-medium text-muted-foreground uppercase">
                              Reason
                            </label>
                            <textarea
                              id="inactivate-reason"
                              value={inactivateReason}
                              onChange={(e) => setInactivateReason(e.target.value)}
                              placeholder="Reason for inactivation (optional)"
                              className="w-full min-h-[80px] rounded-md border bg-background px-3 py-2 text-sm resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                          </div>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={handleInactivate}>
                              Inactivate
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    ) : (
                      <Button variant="outline" size="sm" onClick={handleReactivate} disabled={saving}>
                        <RotateCcw className="h-3.5 w-3.5 mr-1" />
                        Reactivate
                      </Button>
                    )}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
