"use client";

import { useState } from "react";
import type { TimelineMemory, TimelineGroup } from "@/lib/api";
import { api, invalidateCache } from "@/lib/api";
import { formatRelativeDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronRight, Plus, Inbox } from "lucide-react";
import { MemoryCard, MemoryDenseRow } from "./memory-card";
import { type Lifecycle, LIFECYCLE_OPTIONS, LC } from "./memory-filters";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function groupByDate(items: TimelineMemory[]): Map<string, TimelineMemory[]> {
  const groups = new Map<string, TimelineMemory[]>();
  for (const item of items) {
    const label = formatRelativeDate(item.created_at);
    const group = groups.get(label) ?? [];
    group.push(item);
    groups.set(label, group);
  }
  return groups;
}

/* ------------------------------------------------------------------ */
/*  Activity Heatmap                                                   */
/* ------------------------------------------------------------------ */

export function ActivityHeatmap({ items }: { items: TimelineMemory[] }) {
  const dayCounts = new Map<string, number>();
  for (const item of items) {
    const d = new Date(item.created_at);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    dayCounts.set(key, (dayCounts.get(key) ?? 0) + 1);
  }

  const days: { key: string; count: number; label: string }[] = [];
  const today = new Date();
  for (let i = 51; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    days.push({
      key,
      count: dayCounts.get(key) ?? 0,
      label: `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}: ${dayCounts.get(key) ?? 0} memories`,
    });
  }

  const maxCount = Math.max(1, ...days.map((d) => d.count));

  function intensity(count: number): string {
    if (count === 0) return "bg-muted/30";
    const ratio = count / maxCount;
    if (ratio < 0.25) return "bg-emerald-900/60";
    if (ratio < 0.5) return "bg-emerald-700/70";
    if (ratio < 0.75) return "bg-emerald-500/80";
    return "bg-emerald-400";
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Activity</span>
        <span className="text-xs text-muted-foreground">{items.length} memories</span>
      </div>
      <div className="flex gap-[3px] flex-wrap">
        {days.map((d) => (
          <div
            key={d.key}
            title={d.label}
            className={`h-3 w-3 rounded-sm ${intensity(d.count)} transition-colors`}
          />
        ))}
      </div>
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <span>Less</span>
        {["bg-muted/30", "bg-emerald-900/60", "bg-emerald-700/70", "bg-emerald-500/80", "bg-emerald-400"].map((c) => (
          <div key={c} className={`h-2.5 w-2.5 rounded-sm ${c}`} />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Type Group Section                                                 */
/* ------------------------------------------------------------------ */

interface TypeGroupSectionProps {
  group: TimelineGroup;
  dense: boolean;
  openSheet: (id: number) => void;
  onAction: (id: number, action: string) => void;
  activeId: number | null;
  activeCardRef: React.RefObject<HTMLDivElement | null>;
}

export function TypeGroupSection({
  group,
  dense,
  openSheet,
  onAction,
  activeId,
  activeCardRef,
}: TypeGroupSectionProps) {
  return (
    <Collapsible defaultOpen className="group/type-group">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted/30 transition-colors rounded-md">
        <ChevronRight className="size-4 transition-transform duration-200 group-data-[state=open]/type-group:rotate-90" />
        <MemoryTypeBadge type={group.type} />
        <span className="flex-1 text-left">{group.type}</span>
        <span className="text-xs tabular-nums">{group.count}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {dense ? (
          <div className="divide-y divide-border">
            {group.items.map((m) => (
              <MemoryDenseRow
                key={m.id}
                memory={m}
                onSelect={openSheet}
                onAction={onAction}
                isActive={m.id === activeId}
                cardRef={activeCardRef}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2 pl-6 pt-1 pb-2">
            {group.items.map((m) => (
              <MemoryCard
                key={m.id}
                memory={m}
                onSelect={openSheet}
                onAction={onAction}
                isActive={m.id === activeId}
                cardRef={activeCardRef}
              />
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

/* ------------------------------------------------------------------ */
/*  Capture Form (ephemeral item creation)                             */
/* ------------------------------------------------------------------ */

interface CaptureFormProps {
  project: string;
  onCaptured: () => void;
}

export function CaptureForm({ project, onCaptured }: CaptureFormProps) {
  const [content, setContent] = useState("");
  const [itemType, setItemType] = useState("thread");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await api.workingMemoryCapture(project, {
        content: content.trim(),
        item_type: itemType,
        author: "human",
      });
      setContent("");
      invalidateCache("/working-memory");
      invalidateCache("/timeline");
      onCaptured();
    } catch {
      // error handling via UI
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card
      className="mb-4"
      style={{
        borderColor: `color-mix(in oklch, ${LC.ephemeral} 30%, transparent)`,
      }}
    >
      <form onSubmit={handleSubmit} className="p-4">
        <div className="flex gap-2 items-start">
          <textarea
            className="flex-1 min-h-[60px] resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            placeholder="What's on your mind? A hypothesis, question, tension, intuition..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                handleSubmit(e);
              }
            }}
          />
          <div className="flex flex-col gap-2">
            <select
              className="rounded-md border border-input bg-background px-2 py-1 text-xs"
              value={itemType}
              onChange={(e) => setItemType(e.target.value)}
            >
              <option value="thread">Thread</option>
              <option value="hypothesis">Hypothesis</option>
              <option value="question">Question</option>
              <option value="tension">Tension</option>
              <option value="connection">Connection</option>
              <option value="intuition">Intuition</option>
            </select>
            <Button
              type="submit"
              size="sm"
              disabled={!content.trim() || submitting}
              style={{
                backgroundColor: `color-mix(in oklch, ${LC.ephemeral} 80%, transparent)`,
                color: "oklch(0.2 0 0)",
              }}
            >
              <Plus className="h-3 w-3 mr-1" />
              Capture
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Smart Empty State                                                  */
/* ------------------------------------------------------------------ */

interface SmartEmptyStateProps {
  days: number;
  hasFilters: boolean;
  lifecycle: Lifecycle;
  onExpandDays: (d: number) => void;
  onClearFilters: () => void;
}

export function SmartEmptyState({
  days,
  hasFilters,
  lifecycle,
  onExpandDays,
  onClearFilters,
}: SmartEmptyStateProps) {
  const isAll = days >= 9999;
  const nextDays = days < 14 ? 30 : days < 90 ? 90 : 9999;
  const lifecycleLabel = lifecycle === "crystallized" ? "crystallized" : lifecycle === "ephemeral" ? "ephemeral" : "";

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground/50 mb-3" />
      <p className="text-sm text-muted-foreground">
        No {lifecycleLabel} memories{isAll ? "" : ` in the last ${days} days`}.
      </p>
      <div className="flex items-center gap-3 mt-3">
        {!isAll && (
          <Button variant="outline" size="sm" onClick={() => onExpandDays(nextDays)}>
            {nextDays >= 9999 ? "Try all time" : `Try ${nextDays}d`}
          </Button>
        )}
        {hasFilters && (
          <Button variant="outline" size="sm" onClick={onClearFilters}>
            Clear filters
          </Button>
        )}
      </div>
    </div>
  );
}
