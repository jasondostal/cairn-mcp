"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type TimelineMemory } from "@/lib/api";
import { formatRelativeDate, formatTime } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { TagList } from "@/components/tag-list";
import { ProjectSelector } from "@/components/project-selector";
import { SkeletonList } from "@/components/skeleton-list";

const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
] as const;

const DAY_PRESETS = [
  { label: "7d", value: 7 },
  { label: "14d", value: 14 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "1y", value: 365 },
] as const;

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

function TimelineCard({
  memory,
  onSelect,
  isActive,
  cardRef,
}: {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
  isActive?: boolean;
  cardRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const content =
    memory.content.length > 200
      ? memory.content.slice(0, 200) + "\u2026"
      : memory.content;

  return (
    <Card
      ref={isActive ? cardRef : undefined}
      className={`transition-colors hover:border-primary/30 cursor-pointer ${isActive ? "border-primary/50 bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      <CardContent className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <MemoryTypeBadge type={memory.memory_type} />
            <span className="text-xs text-muted-foreground">
              {memory.project}
            </span>
          </div>
          <div className="shrink-0">
            <ImportanceBadge importance={memory.importance} />
          </div>
        </div>

        {memory.summary && (
          <p className="text-sm font-medium">{memory.summary}</p>
        )}

        <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {content}
        </p>

        <TagList tags={memory.tags} />

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>#{memory.id}</span>
          <span>&middot;</span>
          <span>{formatTime(memory.created_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function TimelinePage() {
  const { projects, selected, setSelected, loading: projectsLoading } = useProjectSelector();
  const [items, setItems] = useState<TimelineMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();
  const activeCardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!showAll && !selected) return;
    setLoading(true);
    setError(null);
    api
      .timeline({
        project: showAll ? undefined : selected,
        type: typeFilter ?? undefined,
        days: String(days),
        limit: "200",
      })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err?.message || "Failed to load timeline"))
      .finally(() => setLoading(false));
  }, [selected, showAll, typeFilter, days]);

  const groups = groupByDate(items);

  const flatItems = useMemo(
    () => Array.from(groups.values()).flat(),
    [groups],
  );

  const { activeIndex } = useKeyboardNav({
    itemCount: flatItems.length,
    onSelect: (i) => openSheet(flatItems[i].id),
    enabled: !loading && items.length > 0,
  });

  const activeId = activeIndex >= 0 ? flatItems[activeIndex]?.id : null;

  // Scroll active card into view on keyboard nav
  useEffect(() => {
    if (activeCardRef.current) {
      activeCardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeIndex]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Timeline</h1>

      {/* Sticky filter toolbar */}
      <div className="sticky top-0 z-10 -mx-4 bg-background/95 backdrop-blur-sm px-4 pb-3 pt-1 space-y-2 border-b border-border md:-mx-6 md:px-6">
        {/* Project filter */}
        <div className="flex gap-1 flex-wrap">
          <Button
            variant={showAll ? "default" : "outline"}
            size="sm"
            onClick={() => setShowAll(true)}
          >
            All
          </Button>
          <ProjectSelector
            projects={projects}
            selected={showAll ? "" : selected}
            onSelect={(name) => { setShowAll(false); setSelected(name); }}
          />
        </div>

        {/* Type filter */}
        <div className="flex gap-1 flex-wrap">
          <Button
            variant={typeFilter === null ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter(null)}
          >
            All types
          </Button>
          {MEMORY_TYPES.map((t) => (
            <Button
              key={t}
              variant={typeFilter === t ? "default" : "outline"}
              size="sm"
              onClick={() => setTypeFilter(t)}
            >
              {t}
            </Button>
          ))}
        </div>

        {/* Days range */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Range</span>
          <div className="flex gap-1">
            {DAY_PRESETS.map((p) => (
              <Button
                key={p.value}
                variant={days === p.value ? "default" : "outline"}
                size="sm"
                onClick={() => setDays(p.value)}
              >
                {p.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {(loading || projectsLoading) && <SkeletonList count={5} />}

      {error && <ErrorState message="Failed to load timeline" detail={error} />}

      {!loading && !projectsLoading && !error && items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No memories in the last {days} days.
        </p>
      )}

      {!loading && !projectsLoading && !error && items.length > 0 && (
        <div className="space-y-6">
          <ActivityHeatmap items={items} />
          {Array.from(groups.entries()).map(([label, memories]) => (
            <div key={label}>
              <h2 className="mb-3 text-sm font-medium text-muted-foreground sticky top-[9.5rem] z-[5] bg-background py-1">
                {label}
                <span className="ml-2 text-xs">({memories.length})</span>
              </h2>
              <div className="space-y-2 border-l-2 border-border pl-4">
                {memories.map((m) => (
                  <TimelineCard
                    key={m.id}
                    memory={m}
                    onSelect={openSheet}
                    isActive={m.id === activeId}
                    cardRef={activeCardRef}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}
