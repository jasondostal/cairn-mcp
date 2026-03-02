"use client";

import {
  api,
  type Status,
  type AnalyticsTimeseries,
  type ModelPerformance as MP,
  type ProjectBreakdown as PB,
  type EntitySparklines,
  type MemoryGrowthResult,
  type HeatmapResult,
} from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { useDashboardLayout } from "@/lib/use-dashboard-layout";
import { useSharedDays } from "@/lib/use-page-filters";
import { PageLayout } from "@/components/page-layout";
import { TimeRangeFilter } from "@/components/time-range-filter";

import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { DashboardGrid } from "@/components/dashboard/dashboard-grid";
import { DashboardToolbar } from "@/components/dashboard/dashboard-toolbar";

export default function Dashboard() {
  const [days, setDays] = useSharedDays(7);
  const daysStr = String(days);
  const granularity = days <= 7 ? "hour" : "day";

  const {
    layouts,
    visibleWidgets,
    isEditing,
    setEditing,
    onLayoutChange,
    removeWidget,
    toggleWidget,
    resetToDefaults,
  } = useDashboardLayout();

  // --- Data fetching: all parallel, each section renders independently ---

  const { data: status, loading: statusLoading, error: statusError } =
    useFetch<Status>(() => api.status(), [daysStr]);

  const { data: sparklines } =
    useFetch<EntitySparklines>(() => api.analyticsSparklines({ days: daysStr }), [daysStr]);

  const { data: timeseries } =
    useFetch<AnalyticsTimeseries>(
      () => api.analyticsTimeseries({ days: daysStr, granularity }),
      [daysStr, granularity],
    );

  const { data: memoryGrowth } =
    useFetch<MemoryGrowthResult>(
      () => api.analyticsMemoryGrowth({ days: daysStr, granularity: "day" }),
      [daysStr],
    );

  const { data: heatmapData } =
    useFetch<HeatmapResult>(() => api.analyticsHeatmap({ days: "365" }), [daysStr]);

  const { data: modelsData } =
    useFetch<{ items: MP[] }>(() => api.analyticsModels({ days: daysStr }), [daysStr]);

  const { data: projectsData } =
    useFetch<{ items: PB[] }>(() => api.analyticsProjects({ days: daysStr }), [daysStr]);

  if (statusLoading) {
    return (
      <PageLayout title="Dashboard">
        <SkeletonList count={4} height="h-20" gap="grid grid-cols-2 gap-4 lg:grid-cols-4" />
      </PageLayout>
    );
  }

  if (statusError) {
    return (
      <PageLayout title="Dashboard">
        <ErrorState message="Failed to load dashboard" detail={statusError} />
      </PageLayout>
    );
  }

  if (!status) return null;

  return (
    <PageLayout
      title="Dashboard"
      filters={
        <div className="flex items-center gap-3">
          <TimeRangeFilter days={days} onChange={setDays} />
          <DashboardToolbar
            isEditing={isEditing}
            visibleWidgets={visibleWidgets}
            onSetEditing={setEditing}
            onToggleWidget={toggleWidget}
            onReset={resetToDefaults}
          />
        </div>
      }
    >
      <DashboardGrid
        layouts={layouts}
        visibleWidgets={visibleWidgets}
        isEditing={isEditing}
        onLayoutChange={onLayoutChange}
        onRemoveWidget={removeWidget}
        data={{
          status,
          sparklines: sparklines ?? null,
          timeseries: timeseries ?? null,
          memoryGrowth: memoryGrowth ?? null,
          heatmapData: heatmapData ?? null,
          modelsData: modelsData ?? null,
          projectsData: projectsData ?? null,
          days,
        }}
      />
    </PageLayout>
  );
}
