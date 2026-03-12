"use client";

import { useState, useMemo } from "react";
import {
  ResponsiveGridLayout,
  useContainerWidth,
  verticalCompactor,
} from "react-grid-layout";
import type {
  Status,
  AnalyticsTimeseries,
  ModelPerformance as MP,
  ProjectBreakdown as PB,
  EntitySparklines,
  MemoryGrowthResult,
  HeatmapResult,
} from "@/lib/api";
import type { DashboardLayouts, BreakpointLayout } from "@/lib/dashboard-registry";
import {
  GRID_COLS,
  GRID_ROW_HEIGHT,
  GRID_MARGIN,
  GRID_BREAKPOINTS,
} from "@/lib/dashboard-registry";
import { DashboardWidget } from "./dashboard-widget";
import { WidgetSkeleton } from "./widget-skeleton";

import { OperationalStrip } from "./operational-strip";
import { EntityGrowthChart } from "./entity-growth-chart";
import { MemoryTypeGrowthChart } from "./memory-type-growth-chart";
import { MemoryTypeBar } from "./memory-type-bar";
import { HealthStrip } from "./health-strip";
import { TokenAreaChart } from "@/components/analytics/token-area-chart";
import { OperationsBarChart } from "@/components/analytics/operations-bar-chart";
import { ActivityHeatmap } from "@/components/analytics/activity-heatmap";
import { ModelPerformance } from "@/components/analytics/model-performance";
import { ProjectBreakdown } from "@/components/analytics/project-breakdown";
import { CostProjection } from "@/components/analytics/cost-projection";
// NOTE: EKG hidden until SSE pipeline is stable — see ca-251
// import { LivePulse } from "./live-pulse";

export interface DashboardData {
  status: Status | null;
  sparklines: EntitySparklines | null;
  timeseries: AnalyticsTimeseries | null;
  memoryGrowth: MemoryGrowthResult | null;
  heatmapData: HeatmapResult | null;
  modelsData: { items: MP[] } | null;
  projectsData: { items: PB[] } | null;
  days: number;
}

interface DashboardGridProps {
  layouts: DashboardLayouts;
  visibleWidgets: string[];
  isEditing: boolean;
  onLayoutChange: (current: BreakpointLayout, all: DashboardLayouts) => void;
  onRemoveWidget: (id: string) => void;
  data: DashboardData;
}

function renderWidget(id: string, data: DashboardData) {
  switch (id) {
    case "operational-strip":
      return <OperationalStrip />;
    case "entity-growth":
      return data.sparklines ? <EntityGrowthChart data={data.sparklines} /> : <WidgetSkeleton />;
    case "memory-type-growth":
      return data.memoryGrowth && data.memoryGrowth.series.length > 0
        ? <MemoryTypeGrowthChart data={data.memoryGrowth} />
        : <WidgetSkeleton />;
    case "token-usage":
      return data.timeseries && data.timeseries.series.length > 0
        ? <TokenAreaChart series={data.timeseries.series} />
        : <WidgetSkeleton />;
    case "activity-heatmap":
      return data.heatmapData
        ? <ActivityHeatmap heatmapData={data.heatmapData.days} />
        : <WidgetSkeleton />;
    case "health-strip":
      return data.status
        ? <HealthStrip
            embedding={data.status.models?.embedding}
            llm={data.status.models?.llm}
            digest={data.status.digest}
          />
        : <WidgetSkeleton />;
    case "operations-volume":
      return data.timeseries && data.timeseries.series.length > 0
        ? <OperationsBarChart series={data.timeseries.series} />
        : <WidgetSkeleton />;
    case "cost-projection":
      return data.modelsData && data.modelsData.items.length > 0
        ? <CostProjection models={data.modelsData.items} days={data.days} />
        : <WidgetSkeleton />;
    case "model-performance":
      return data.modelsData
        ? <ModelPerformance items={data.modelsData.items} />
        : <WidgetSkeleton />;
    case "project-breakdown":
      return data.projectsData
        ? <ProjectBreakdown items={data.projectsData.items} />
        : <WidgetSkeleton />;
    case "memory-type-bar":
      return data.status
        ? <MemoryTypeBar types={data.status.types} />
        : <WidgetSkeleton />;
    // NOTE: EKG hidden until SSE pipeline is stable — see ca-251
    // case "live-pulse":
    //   return <LivePulse />;
    default:
      return <WidgetSkeleton />;
  }
}

export function DashboardGrid({
  layouts,
  visibleWidgets,
  isEditing,
  onLayoutChange,
  onRemoveWidget,
  data,
}: DashboardGridProps) {
  const { containerRef, width } = useContainerWidth();
  const [breakpoint, setBreakpoint] = useState("lg");
  const isSmall = breakpoint === "sm";

  // Filter layouts to only include visible widgets
  const filteredLayouts = useMemo(() => {
    const visible = new Set(visibleWidgets);
    const result: DashboardLayouts = {};
    for (const [bp, items] of Object.entries(layouts)) {
      result[bp] = (items ?? []).filter((l) => visible.has(l.i));
    }
    return result;
  }, [layouts, visibleWidgets]);

  return (
    <div ref={containerRef}>
      <ResponsiveGridLayout
        width={width}
        layouts={filteredLayouts}
        breakpoints={GRID_BREAKPOINTS}
        cols={GRID_COLS}
        rowHeight={GRID_ROW_HEIGHT}
        margin={GRID_MARGIN}
        dragConfig={{
          enabled: isEditing && !isSmall,
          handle: ".dashboard-drag-handle",
        }}
        resizeConfig={{ enabled: isEditing && !isSmall }}
        onLayoutChange={onLayoutChange}
        onBreakpointChange={setBreakpoint}
        compactor={verticalCompactor}
      >
        {visibleWidgets.map((id) => (
          <div key={id}>
            <DashboardWidget id={id} isEditing={isEditing} onRemove={onRemoveWidget}>
              {renderWidget(id, data)}
            </DashboardWidget>
          </div>
        ))}
      </ResponsiveGridLayout>
    </div>
  );
}
