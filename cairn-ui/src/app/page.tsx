"use client";

import { useState } from "react";
import Link from "next/link";
import {
  api,
  type Status,
  type Project,
  type AnalyticsTimeseries,
  type ModelPerformance as MP,
  type ProjectBreakdown as PB,
  type EntitySparklines,
  type MemoryGrowthResult,
  type HeatmapResult,
} from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLayout } from "@/components/page-layout";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";

import { SparklineKpiStrip } from "@/components/dashboard/sparkline-kpi-strip";
import { MemoryTypeGrowthChart } from "@/components/dashboard/memory-type-growth-chart";
import { HealthStrip } from "@/components/dashboard/health-strip";
import { TokenAreaChart } from "@/components/analytics/token-area-chart";
import { OperationsBarChart } from "@/components/analytics/operations-bar-chart";
import { ActivityHeatmap } from "@/components/analytics/activity-heatmap";
import { ModelPerformance } from "@/components/analytics/model-performance";
import { ProjectBreakdown } from "@/components/analytics/project-breakdown";
import { CostProjection } from "@/components/analytics/cost-projection";

const DAY_PRESETS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
] as const;

function TypeBadge({ type, count }: { type: string; count: number }) {
  return (
    <Badge variant="secondary" className="gap-1 font-mono text-xs">
      {type}
      <span className="text-muted-foreground">{count}</span>
    </Badge>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/projects/${encodeURIComponent(project.name)}`}>
      <Card className="transition-colors hover:border-primary/30">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm font-medium">{project.name}</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-semibold tabular-nums">
              {project.memory_count}
            </span>
            <span className="text-sm text-muted-foreground">memories</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function Dashboard() {
  const [days, setDays] = useState(7);
  const daysStr = String(days);
  const granularity = days <= 7 ? "hour" : "day";

  // --- Data fetching: all parallel, each section renders independently ---

  const { data: status, loading: statusLoading, error: statusError } =
    useFetch<Status>(() => api.status(), [daysStr]);

  const { data: projects } =
    useFetch<Project[]>(() => api.projects().then((r) => r.items), [daysStr]);

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
      }
    >
      <div className="space-y-4">
        {/* KPI Strip with sparklines */}
        {sparklines && <SparklineKpiStrip data={sparklines} />}

        {/* Operations + Token charts — 2 col */}
        {timeseries && timeseries.series.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <OperationsBarChart series={timeseries.series} />
            <TokenAreaChart series={timeseries.series} />
          </div>
        )}

        {/* Memory Type Growth + Activity Heatmap */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {memoryGrowth && memoryGrowth.series.length > 0 && (
            <MemoryTypeGrowthChart data={memoryGrowth} />
          )}
          {heatmapData && <ActivityHeatmap heatmapData={heatmapData.days} />}
        </div>

        {/* Health strip — compact horizontal */}
        <HealthStrip
          embedding={status.models?.embedding}
          llm={status.models?.llm}
          digest={status.digest}
        />

        {/* Model Performance + Project Breakdown — 2 col tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {modelsData && <ModelPerformance items={modelsData.items} />}
          {projectsData && <ProjectBreakdown items={projectsData.items} />}
        </div>

        {/* Cost Projection — full width */}
        {modelsData && modelsData.items.length > 0 && (
          <CostProjection models={modelsData.items} days={days} />
        )}

        {/* Memory Types badges */}
        <div>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">
            Memory Types
          </h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(status.types)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <TypeBadge key={type} type={type} count={count} />
              ))}
          </div>
        </div>

        {/* Projects Grid — pushed to bottom */}
        <div>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">
            Projects
          </h2>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
            {(projects || []).map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
