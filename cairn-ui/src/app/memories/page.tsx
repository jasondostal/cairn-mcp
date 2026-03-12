"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api, type TimelineMemory, type TimelineGroup, invalidateCache } from "@/lib/api";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { usePageFilters } from "@/lib/use-page-filters";
import { DenseToggle } from "@/components/page-filters";
import { toast } from "sonner";
import { MultiSelect } from "@/components/ui/multi-select";
import { TimeRangeFilter } from "@/components/time-range-filter";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { projectColor } from "@/lib/colors";

import {
  MEMORY_TYPES,
  MEMORIES_TIME_PRESETS,
  SORT_OPTIONS,
  VIEW_OPTIONS,
  LIFECYCLE_OPTIONS,
  type Lifecycle,
  OklchToggle,
  ActiveFilterBar,
  type ActiveFilter,
} from "@/components/memories/memory-filters";

import { MemoryCard, MemoryDenseRow } from "@/components/memories/memory-card";
import {
  groupByDate,
  ActivityHeatmap,
  TypeGroupSection,
  CaptureForm,
  SmartEmptyState,
} from "@/components/memories/memory-list";

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

  // Sync state -> URL (debounced via effect)
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
      toast.error("Action failed");
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
            {/* Type filter — hidden on mobile to reduce toolbar height */}
            <span className="hidden md:contents">
              <MultiSelect
                options={typeOptions}
                value={filters.typeFilter}
                onValueChange={filters.setTypeFilter}
                placeholder="All types"
                searchPlaceholder="Search…"
                maxCount={2}
              />
            </span>
            <OklchToggle value={lifecycle} options={LIFECYCLE_OPTIONS} onChange={setLifecycle} />

            {/* === DIVIDER (desktop only) === */}
            <div className="hidden md:block h-6 w-px bg-border mx-0.5" />

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
