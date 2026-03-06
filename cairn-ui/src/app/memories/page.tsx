"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { api, type TimelineMemory, type TimelineGroup, invalidateCache } from "@/lib/api";
import { formatRelativeDate, formatTime } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { usePageFilters } from "@/lib/use-page-filters";
import { DenseToggle } from "@/components/page-filters";
import { MultiSelect } from "@/components/ui/multi-select";
import { Card, CardContent } from "@/components/ui/card";

import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { TimeRangeFilter } from "@/components/time-range-filter";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ProjectPill } from "@/components/project-pill";
import { TagList } from "@/components/tag-list";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { projectColor, scoreColor, salienceColor } from "@/lib/colors";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronRight, Network, Pin, Zap, Archive, Plus, Lightbulb, X, Inbox } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
  // Ephemeral types
  "hypothesis", "question", "tension", "connection", "thread", "intuition",
] as const;

const MEMORIES_TIME_PRESETS = [
  { label: "7d",  value: 7,   color: "oklch(0.72 0.17 135)" },  // mint
  { label: "14d", value: 14,  color: "oklch(0.70 0.17 220)" },  // sky
  { label: "30d", value: 30,  color: "oklch(0.68 0.18 270)" },  // periwinkle
  { label: "90d", value: 90,  color: "oklch(0.66 0.19 320)" },  // orchid
  { label: "All", value: 9999, color: "oklch(0.70 0.17 350)" },  // blush
];

const SORT_OPTIONS = [
  { label: "Recent",    value: "recent",    color: "oklch(0.72 0.18 240)" },  // blue
  { label: "Important", value: "important", color: "oklch(0.70 0.19 15)" },   // rose
  { label: "Relevance", value: "relevance", color: "oklch(0.68 0.19 300)" },  // violet
] as const;

const VIEW_OPTIONS = [
  { label: "Chrono",  value: "chrono",  color: "oklch(0.72 0.18 145)" },  // emerald
  { label: "By type", value: "type",    color: "oklch(0.70 0.19 55)" },   // tangerine
] as const;

/* OKLCH lifecycle toggle colors */
const LC = {
  all:          "oklch(0.72 0.19 165)",   // teal
  crystallized: "oklch(0.65 0.18 260)",   // indigo
  ephemeral:    "oklch(0.78 0.18 75)",    // amber
} as const;

/* projectColor, scoreColor, salienceColor — sourced from lib/colors */

type Lifecycle = "all" | "crystallized" | "ephemeral";

const LIFECYCLE_OPTIONS: { label: string; value: Lifecycle; color: string }[] = [
  { label: "All",          value: "all",          color: LC.all },
  { label: "Crystallized", value: "crystallized",  color: LC.crystallized },
  { label: "Ephemeral",    value: "ephemeral",     color: LC.ephemeral },
];

/* Ephemeral type styles removed — MemoryTypeBadge now handles both crystallized and ephemeral */

/* ------------------------------------------------------------------ */
/*  Lifecycle Toggle                                                   */
/* ------------------------------------------------------------------ */

function LifecycleToggle({
  value,
  onChange,
}: {
  value: Lifecycle;
  onChange: (v: Lifecycle) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => { if (v) onChange(v as Lifecycle); }}
    >
      {LIFECYCLE_OPTIONS.map((opt) => (
        <ToggleGroupItem
          key={opt.value}
          value={opt.value}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            value === opt.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${opt.color} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${opt.color} 40%, transparent)`,
                  color: opt.color,
                }
              : undefined
          }
        >
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/* ------------------------------------------------------------------ */
/*  Activity Heatmap                                                   */
/* ------------------------------------------------------------------ */

function ActivityHeatmap({ items }: { items: TimelineMemory[] }) {
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
/*  Cluster Tag                                                        */
/* ------------------------------------------------------------------ */

function ClusterTag({ cluster }: { cluster: { id: number; label: string; size: number } }) {
  return (
    <Link
      href={`/search?q=${encodeURIComponent(cluster.label)}`}
      className="inline-flex items-center gap-1 rounded-full bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <Network className="size-3" />
      {cluster.label}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Salience Bar (ephemeral items)                                     */
/* ------------------------------------------------------------------ */

function SalienceBar({ salience }: { salience: number }) {
  return (
    <div
      className="w-1 rounded-full self-stretch shrink-0"
      style={{
        backgroundColor: LC.ephemeral,
        opacity: Math.max(0.15, salience),
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Ephemeral Actions (boost / pin / archive)                          */
/* ------------------------------------------------------------------ */

function EphemeralActions({
  memory,
  onAction,
  size = "default",
}: {
  memory: TimelineMemory;
  onAction: (id: number, action: string) => void;
  size?: "default" | "dense";
}) {
  const btnCls = size === "dense" ? "h-5 w-5 p-0" : "h-6 w-6 p-0";
  const iconCls = size === "dense" ? "h-2.5 w-2.5" : "h-3 w-3";

  return (
    <div className={`flex ${size === "dense" ? "gap-0.5" : "gap-1"}`}>
      <Button variant="ghost" size="sm" className={btnCls} title="Boost salience"
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, "boost"); }}>
        <Zap className={iconCls} />
      </Button>
      <Button variant="ghost" size="sm" className={btnCls} title={memory.pinned ? "Unpin" : "Pin"}
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, memory.pinned ? "unpin" : "pin"); }}>
        <Pin className={iconCls} />
      </Button>
      <Button variant="ghost" size="sm" className={btnCls} title="Archive"
        onClick={(e) => { e.stopPropagation(); onAction(memory.id, "archive"); }}>
        <Archive className={iconCls} />
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function isEphemeral(m: TimelineMemory): boolean {
  return m.salience != null;
}

function groupByDate(items: TimelineMemory[]): Map<string, TimelineMemory[]> {
  const groups = new Map<string, TimelineMemory[]>();
  for (const item of items) {
    const label = formatRelativeDate(item.created_at);
    const group = groups.get(label) ?? [];
    group.push(item);
    groups.set(label, group);
  }
  return groups;
}

/* ProjectPill — sourced from components/project-pill.tsx */

/* ------------------------------------------------------------------ */
/*  Score Bar (importance or salience)                                  */
/* ------------------------------------------------------------------ */

function ScoreBar({ value, variant }: { value: number; variant: "importance" | "salience" }) {
  const c = variant === "salience" ? salienceColor(value) : scoreColor(value);
  const pct = (value * 100).toFixed(0);
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <div className="w-10 h-1.5 rounded-full bg-muted/40 overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.max(5, value * 100)}%`, backgroundColor: c }}
        />
      </div>
      <span className="font-mono text-[11px] tabular-nums w-7 text-right" style={{ color: c }}>
        {variant === "salience" ? `${pct}%` : value.toFixed(2)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Memory Card                                                        */
/* ------------------------------------------------------------------ */

function MemoryCard({
  memory,
  onSelect,
  onAction,
  isActive,
  cardRef,
}: {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
  onAction: (id: number, action: string) => void;
  isActive?: boolean;
  cardRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const content =
    memory.content.length > 200
      ? memory.content.slice(0, 200) + "\u2026"
      : memory.content;
  const eph = isEphemeral(memory);


  return (
    <Card
      ref={isActive ? cardRef : undefined}
      className={`transition-colors hover:border-primary/30 cursor-pointer ${isActive ? "border-primary/50 bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      <div className="flex">
        {eph && <SalienceBar salience={memory.salience!} />}
        <CardContent className={`space-y-2 p-4 flex-1 min-w-0 ${eph ? "pl-3" : ""}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              {eph && <Lightbulb className="h-4 w-4 text-muted-foreground shrink-0" />}
              <MemoryTypeBadge type={memory.memory_type} />
              <ProjectPill name={memory.project} />
              {eph && memory.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
            </div>
            <div className="shrink-0">
              {eph ? (
                <ScoreBar value={memory.salience!} variant="salience" />
              ) : (
                <ScoreBar value={memory.importance} variant="importance" />
              )}
            </div>
          </div>

          {memory.summary && !eph && (
            <p className="text-sm font-medium">{memory.summary}</p>
          )}

          <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
            {content}
          </p>

          {!eph && (
            <div className="flex items-center gap-2 flex-wrap">
              <TagList tags={memory.tags} />
              {memory.cluster && <ClusterTag cluster={memory.cluster} />}
            </div>
          )}

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>#{memory.id}</span>
            {eph && memory.author && (
              <>
                <span>&middot;</span>
                <span>{memory.author}</span>
              </>
            )}
            <span>&middot;</span>
            <span>{formatTime(memory.created_at)}</span>
            {eph && (
              <div className="ml-auto">
                <EphemeralActions memory={memory} onAction={onAction} />
              </div>
            )}
          </div>
        </CardContent>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Memory Dense Row                                                   */
/* ------------------------------------------------------------------ */

function MemoryDenseRow({
  memory,
  onSelect,
  onAction,
  isActive,
  cardRef,
}: {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
  onAction: (id: number, action: string) => void;
  isActive?: boolean;
  cardRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const eph = isEphemeral(memory);


  return (
    <div
      ref={isActive ? cardRef : undefined}
      className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer ${isActive ? "bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      {eph && (
        <div
          className="w-1 h-4 rounded-full shrink-0"
          style={{
            backgroundColor: LC.ephemeral,
            opacity: Math.max(0.15, memory.salience!),
          }}
        />
      )}
      <span className="font-mono text-xs text-muted-foreground shrink-0">#{memory.id}</span>
      <MemoryTypeBadge type={memory.memory_type} />
      {eph && memory.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
      <span className="flex-1 truncate">{memory.summary || memory.content}</span>
      <ProjectPill name={memory.project} />
      {eph ? (
        <ScoreBar value={memory.salience!} variant="salience" />
      ) : (
        <ScoreBar value={memory.importance} variant="importance" />
      )}
      <span className="text-xs text-muted-foreground shrink-0">{formatTime(memory.created_at)}</span>
      {eph && <EphemeralActions memory={memory} onAction={onAction} size="dense" />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Type Group Section                                                 */
/* ------------------------------------------------------------------ */

function TypeGroupSection({
  group,
  dense,
  openSheet,
  onAction,
  activeId,
  activeCardRef,
}: {
  group: TimelineGroup;
  dense: boolean;
  openSheet: (id: number) => void;
  onAction: (id: number, action: string) => void;
  activeId: number | null;
  activeCardRef: React.RefObject<HTMLDivElement | null>;
}) {
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

function CaptureForm({
  project,
  onCaptured,
}: {
  project: string;
  onCaptured: () => void;
}) {
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
/*  OKLCH Toggle (reusable)                                            */
/* ------------------------------------------------------------------ */

function OklchToggle<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: readonly { label: string; value: T; color: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => { if (v) onChange(v as T); }}
    >
      {options.map((opt) => (
        <ToggleGroupItem
          key={opt.value}
          value={opt.value}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            value === opt.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${opt.color} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${opt.color} 40%, transparent)`,
                  color: opt.color,
                }
              : undefined
          }
        >
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/* ------------------------------------------------------------------ */
/*  Active Filter Pills                                                */
/* ------------------------------------------------------------------ */

interface ActiveFilter {
  key: string;
  label: string;
  color?: string;
  onRemove: () => void;
}

function ActiveFilterBar({ filters }: { filters: ActiveFilter[] }) {
  if (filters.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-2">
      <span className="text-[11px] text-muted-foreground/70">Active:</span>
      {filters.map((f) => (
        <button
          key={f.key}
          onClick={f.onRemove}
          className="group inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors hover:bg-destructive/10"
          style={f.color ? {
            backgroundColor: `color-mix(in oklch, ${f.color} 12%, transparent)`,
            borderColor: `color-mix(in oklch, ${f.color} 30%, transparent)`,
            border: "1px solid",
            color: f.color,
          } : {
            backgroundColor: "hsl(var(--muted))",
            color: "hsl(var(--muted-foreground))",
          }}
        >
          {f.label}
          <X className="h-2.5 w-2.5 opacity-50 group-hover:opacity-100" />
        </button>
      ))}
      {filters.length > 1 && (
        <button
          onClick={() => filters.forEach((f) => f.onRemove())}
          className="text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors ml-1"
        >
          Clear all
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Smart Empty State                                                  */
/* ------------------------------------------------------------------ */

function SmartEmptyState({
  days,
  hasFilters,
  lifecycle,
  onExpandDays,
  onClearFilters,
}: {
  days: number;
  hasFilters: boolean;
  lifecycle: Lifecycle;
  onExpandDays: (d: number) => void;
  onClearFilters: () => void;
}) {
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

/* ------------------------------------------------------------------ */
/*  URL State Sync                                                     */
/* ------------------------------------------------------------------ */

function useUrlState() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const readUrl = useCallback(() => ({
    lifecycle: (searchParams.get("lifecycle") as Lifecycle) || undefined,
    sort: searchParams.get("sort") || undefined,
    days: searchParams.get("days") ? Number(searchParams.get("days")) : undefined,
    view: searchParams.get("view") || undefined,
    project: searchParams.get("project") || undefined,
    type: searchParams.get("type") || undefined,
  }), [searchParams]);

  const writeUrl = useCallback((state: Record<string, string | undefined>) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) {
      if (v && v !== "all" && v !== "recent" && v !== "chrono" && v !== "7" && v !== "9999") {
        params.set(k, v);
      }
    }
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "/memories", { scroll: false });
  }, [router]);

  return { readUrl, writeUrl };
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function MemoriesPage() {
  const filters = usePageFilters({ defaultDays: 7 });
  const { readUrl, writeUrl } = useUrlState();

  // Initialize from URL params (override localStorage on first load)
  const [initialized, setInitialized] = useState(false);
  const urlState = readUrl();

  const [sort, setSort] = useState(urlState.sort || "recent");
  const [groupByType, setGroupByType] = useState(urlState.view === "type");
  const [lifecycle, setLifecycle] = useState<Lifecycle>(urlState.lifecycle || "all");

  // Apply URL overrides to shared filters on first mount
  useEffect(() => {
    if (initialized) return;
    if (urlState.days) filters.setDays(urlState.days);
    if (urlState.project) filters.setProjectFilter(urlState.project.split(","));
    if (urlState.type) filters.setTypeFilter(urlState.type.split(","));
    setInitialized(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const days = filters.days ?? 7;

  // Sync state → URL (debounced via effect)
  useEffect(() => {
    if (!initialized) return;
    writeUrl({
      lifecycle,
      sort,
      days: String(days),
      view: groupByType ? "type" : "chrono",
      project: filters.projectFilter.length ? filters.projectFilter.join(",") : undefined,
      type: filters.typeFilter.length ? filters.typeFilter.join(",") : undefined,
    });
  }, [lifecycle, sort, days, groupByType, filters.projectFilter, filters.typeFilter, initialized, writeUrl]);

  const [items, setItems] = useState<TimelineMemory[]>([]);
  const [typeGroups, setTypeGroups] = useState<TimelineGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();
  const activeCardRef = useRef<HTMLDivElement | null>(null);

  const typeOptions = MEMORY_TYPES.map((t) => ({ value: t, label: t }));

  const project = filters.showAllProjects ? undefined : filters.projectFilter.join(",");

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .timeline({
        project,
        type: filters.typeFilter.length ? filters.typeFilter.join(",") : undefined,
        days: String(days),
        sort,
        group_by: groupByType ? "type" : "none",
        include_clusters: "true",
        limit: "200",
        ephemeral: lifecycle === "all" ? undefined : lifecycle === "ephemeral" ? "true" : "false",
      })
      .then((data) => {
        if ("groups" in data) {
          setTypeGroups(data.groups);
          setItems(data.groups.flatMap((g) => g.items));
        } else {
          setItems(data.items);
          setTypeGroups([]);
        }
      })
      .catch((err) => setError(err?.message || "Failed to load memories"))
      .finally(() => setLoading(false));
  }, [project, filters.typeFilter, days, sort, groupByType, lifecycle]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const dateGroups = useMemo(() => groupByDate(items), [items]);

  const flatItems = useMemo(
    () => groupByType
      ? typeGroups.flatMap((g) => g.items)
      : Array.from(dateGroups.values()).flat(),
    [groupByType, typeGroups, dateGroups],
  );

  const { activeIndex } = useKeyboardNav({
    itemCount: flatItems.length,
    onSelect: (i) => openSheet(flatItems[i].id),
    enabled: !loading && flatItems.length > 0,
  });

  const activeId = activeIndex >= 0 ? flatItems[activeIndex]?.id : null;

  useEffect(() => {
    if (activeCardRef.current) {
      activeCardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeIndex]);

  const handleEphemeralAction = useCallback(async (id: number, action: string) => {
    try {
      if (action === "boost") await api.workingMemoryBoost(id);
      else if (action === "pin") await api.workingMemoryPin(id);
      else if (action === "unpin") await api.workingMemoryUnpin(id);
      else if (action === "archive") await api.workingMemoryArchive(id);
      invalidateCache("/working-memory");
      invalidateCache("/timeline");
      loadData();
    } catch {
      // swallow
    }
  }, [loadData]);

  // --- Active filter pills ---
  const activeFilters: ActiveFilter[] = useMemo(() => {
    const pills: ActiveFilter[] = [];
    for (const p of filters.projectFilter) {
      pills.push({
        key: `project:${p}`,
        label: p,
        color: projectColor(p),
        onRemove: () => filters.setProjectFilter(filters.projectFilter.filter((x) => x !== p)),
      });
    }
    for (const t of filters.typeFilter) {
      pills.push({
        key: `type:${t}`,
        label: t,
        onRemove: () => filters.setTypeFilter(filters.typeFilter.filter((x) => x !== t)),
      });
    }
    if (lifecycle !== "all") {
      const opt = LIFECYCLE_OPTIONS.find((o) => o.value === lifecycle)!;
      pills.push({
        key: "lifecycle",
        label: opt.label,
        color: opt.color,
        onRemove: () => setLifecycle("all"),
      });
    }
    return pills;
  }, [filters, lifecycle]);

  const hasActiveFilters = activeFilters.length > 0;
  const filterCount = activeFilters.length;

  const clearAllFilters = useCallback(() => {
    filters.setProjectFilter([]);
    filters.setTypeFilter([]);
    setLifecycle("all");
  }, [filters]);

  return (
    <PageLayout
      title="Memories"
      titleExtra={
        <div className="flex items-center gap-2">
          {filterCount > 0 && (
            <span className="inline-flex items-center justify-center rounded-full bg-primary/10 text-primary text-[11px] font-medium h-5 min-w-5 px-1.5">
              {filterCount}
            </span>
          )}
          <DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />
        </div>
      }
      filters={
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* === DATA FILTERS (what) === */}
            <MultiSelect
              options={filters.projectOptions}
              value={filters.projectFilter}
              onValueChange={filters.setProjectFilter}
              placeholder="All projects"
              searchPlaceholder="Search projects…"
              maxCount={2}
            />
            <MultiSelect
              options={typeOptions}
              value={filters.typeFilter}
              onValueChange={filters.setTypeFilter}
              placeholder="All types"
              searchPlaceholder="Search…"
              maxCount={2}
            />
            <OklchToggle value={lifecycle} options={LIFECYCLE_OPTIONS} onChange={setLifecycle} />

            {/* === DIVIDER === */}
            <div className="h-6 w-px bg-border mx-0.5" />

            {/* === DISPLAY CONTROLS (how) === */}
            <OklchToggle value={sort} options={SORT_OPTIONS} onChange={setSort} />
            <TimeRangeFilter days={days} onChange={filters.setDays} presets={MEMORIES_TIME_PRESETS} />
            <OklchToggle
              value={groupByType ? "type" : "chrono"}
              options={VIEW_OPTIONS}
              onChange={(v: string) => setGroupByType(v === "type")}
            />
          </div>

          {/* Active filter pills */}
          <ActiveFilterBar filters={activeFilters} />
        </div>
      }
    >
      {/* Capture form — shown when ephemeral mode or all mode */}
      {lifecycle !== "crystallized" && project && (
        <CaptureForm project={project} onCaptured={loadData} />
      )}

      {(loading || filters.projectsLoading) && <SkeletonList count={5} />}

      {error && <ErrorState message="Failed to load memories" detail={error} />}

      {!loading && !filters.projectsLoading && !error && items.length === 0 && (
        <SmartEmptyState
          days={days}
          hasFilters={hasActiveFilters}
          lifecycle={lifecycle}
          onExpandDays={filters.setDays}
          onClearFilters={clearAllFilters}
        />
      )}

      {!loading && !filters.projectsLoading && !error && items.length > 0 && (
        <div className="space-y-6">
          <ActivityHeatmap items={items} />

          {groupByType ? (
            /* --- Group by type view --- */
            <div className="space-y-1 rounded-md border border-border">
              {typeGroups.map((group) => (
                <TypeGroupSection
                  key={group.type}
                  group={group}
                  dense={filters.dense}
                  openSheet={openSheet}
                  onAction={handleEphemeralAction}
                  activeId={activeId}
                  activeCardRef={activeCardRef}
                />
              ))}
            </div>
          ) : filters.dense ? (
            /* --- Dense chronological view --- */
            <div className="rounded-md border border-border divide-y divide-border">
              {Array.from(dateGroups.entries()).map(([label, memories]) => (
                <div key={label}>
                  <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted/30">
                    {label} <span className="ml-1">({memories.length})</span>
                  </div>
                  {memories.map((m) => (
                    <MemoryDenseRow
                      key={m.id}
                      memory={m}
                      onSelect={openSheet}
                      onAction={handleEphemeralAction}
                      isActive={m.id === activeId}
                      cardRef={activeCardRef}
                    />
                  ))}
                </div>
              ))}
            </div>
          ) : (
            /* --- Card chronological view --- */
            Array.from(dateGroups.entries()).map(([label, memories]) => (
              <div key={label}>
                <h2 className="mb-3 text-sm font-medium text-muted-foreground sticky top-0 z-[5] -mx-4 px-4 md:-mx-6 md:px-6 bg-background py-1.5 border-b border-border">
                  {label}
                  <span className="ml-2 text-xs">({memories.length})</span>
                </h2>
                <div className="space-y-2 border-l-2 border-border pl-4">
                  {memories.map((m) => (
                    <MemoryCard
                      key={m.id}
                      memory={m}
                      onSelect={openSheet}
                      onAction={handleEphemeralAction}
                      isActive={m.id === activeId}
                      cardRef={activeCardRef}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
