"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, type TimelineMemory, type TimelineGroup } from "@/lib/api";
import { formatRelativeDate, formatTime } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TimeRangeFilter } from "@/components/time-range-filter";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { TagList } from "@/components/tag-list";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronRight, Network } from "lucide-react";

const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
] as const;

const MEMORIES_TIME_PRESETS = [
  { label: "7d", value: 7 },
  { label: "14d", value: 14 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "1y", value: 365 },
];

const SORT_OPTIONS = [
  { label: "Recent", value: "recent" },
  { label: "Important", value: "important" },
  { label: "Relevance", value: "relevance" },
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

function MemoryCard({
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

        <div className="flex items-center gap-2 flex-wrap">
          <TagList tags={memory.tags} />
          {memory.cluster && <ClusterTag cluster={memory.cluster} />}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>#{memory.id}</span>
          <span>&middot;</span>
          <span>{formatTime(memory.created_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function MemoryDenseRow({
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
  return (
    <div
      ref={isActive ? cardRef : undefined}
      className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer ${isActive ? "bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      <span className="font-mono text-xs text-muted-foreground shrink-0">#{memory.id}</span>
      <MemoryTypeBadge type={memory.memory_type} />
      <span className="flex-1 truncate">{memory.summary || memory.content}</span>
      <span className="text-xs text-muted-foreground shrink-0">{memory.project}</span>
      <ImportanceBadge importance={memory.importance} />
      <span className="text-xs text-muted-foreground shrink-0">{formatTime(memory.created_at)}</span>
    </div>
  );
}

function TypeGroupSection({
  group,
  dense,
  openSheet,
  activeId,
  activeCardRef,
}: {
  group: TimelineGroup;
  dense: boolean;
  openSheet: (id: number) => void;
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

export default function MemoriesPage() {
  const filters = usePageFilters({ defaultDays: 7 });
  const days = filters.days ?? 7;
  const [items, setItems] = useState<TimelineMemory[]>([]);
  const [typeGroups, setTypeGroups] = useState<TimelineGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState("recent");
  const [groupByType, setGroupByType] = useState(false);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();
  const activeCardRef = useRef<HTMLDivElement | null>(null);

  const typeOptions = MEMORY_TYPES.map((t) => ({ value: t, label: t }));

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .timeline({
        project: filters.showAllProjects ? undefined : filters.projectFilter.join(","),
        type: filters.typeFilter.length ? filters.typeFilter.join(",") : undefined,
        days: String(days),
        sort,
        group_by: groupByType ? "type" : "none",
        include_clusters: "true",
        limit: "200",
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
  }, [filters.projectFilter, filters.typeFilter, days, sort, groupByType, filters.showAllProjects]);

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

  return (
    <PageLayout
      title="Memories"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={
        <PageFilters
          filters={filters}
          typeOptions={typeOptions}
          typePlaceholder="All types"
          extra={
            <div className="flex items-center gap-4 flex-wrap">
              {/* Sort */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Sort</span>
                <div className="flex gap-1">
                  {SORT_OPTIONS.map((s) => (
                    <Button
                      key={s.value}
                      variant={sort === s.value ? "default" : "outline"}
                      size="sm"
                      onClick={() => setSort(s.value)}
                    >
                      {s.label}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Day range */}
              <TimeRangeFilter days={days} onChange={filters.setDays} presets={MEMORIES_TIME_PRESETS} />

              {/* Group by type toggle */}
              <Button
                variant={groupByType ? "default" : "outline"}
                size="sm"
                onClick={() => setGroupByType((g) => !g)}
              >
                By type
              </Button>
            </div>
          }
        />
      }
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={5} />}

      {error && <ErrorState message="Failed to load memories" detail={error} />}

      {!loading && !filters.projectsLoading && !error && items.length === 0 && (
        <EmptyState message={`No memories in the last ${days} days.`} />
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
