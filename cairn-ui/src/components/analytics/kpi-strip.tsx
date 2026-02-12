"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { AnalyticsOverview, SparklinePoint } from "@/lib/api";
import { AreaChart, Area, ResponsiveContainer } from "recharts";

function MiniSparkline({ data, color }: { data: SparklinePoint[]; color: string }) {
  if (!data.length) return <div className="h-[40px]" />;
  return (
    <ResponsiveContainer width="100%" height={40}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#grad-${color})`}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function formatValue(key: string, value: number): string {
  if (key === "tokens") {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
    return String(value);
  }
  if (key === "avg_latency") return `${value.toFixed(0)}ms`;
  if (key === "error_rate") return `${value.toFixed(1)}%`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

const KPI_COLORS: Record<string, string> = {
  operations: "hsl(var(--chart-1))",
  tokens: "hsl(var(--chart-2))",
  avg_latency: "hsl(var(--chart-3))",
  error_rate: "hsl(var(--chart-5))",
};

const SPARKLINE_MAP: Record<string, keyof AnalyticsOverview["sparklines"]> = {
  operations: "operations",
  tokens: "tokens",
  avg_latency: "operations",
  error_rate: "errors",
};

export function KpiStrip({ data }: { data: AnalyticsOverview }) {
  const entries = Object.entries(data.kpis) as [string, { value: number; label: string }][];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {entries.map(([key, kpi]) => (
        <Card key={key}>
          <CardContent className="p-4 space-y-1">
            <p className="text-xs text-muted-foreground">{kpi.label}</p>
            <p className="text-2xl font-semibold tabular-nums">
              {formatValue(key, kpi.value)}
            </p>
            <MiniSparkline
              data={data.sparklines[SPARKLINE_MAP[key]] ?? []}
              color={KPI_COLORS[key] ?? "hsl(var(--chart-1))"}
            />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
