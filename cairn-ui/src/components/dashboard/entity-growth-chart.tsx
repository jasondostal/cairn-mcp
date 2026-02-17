"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { EntitySparklines, SparklinePoint } from "@/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

interface MetricDef {
  key: keyof EntitySparklines["totals"];
  label: string;
  color: string;
}

const METRIC_DEFS: MetricDef[] = [
  { key: "memories", label: "Memories", color: CHART_COLORS[0] },
  { key: "projects", label: "Projects", color: CHART_COLORS[2] },
  { key: "clusters", label: "Clusters", color: CHART_COLORS[3] },
];

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function formatTick(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Merge per-metric sparklines into a unified time series for Recharts. */
function mergeSeries(
  sparklines: EntitySparklines["sparklines"],
): Record<string, number | string>[] {
  const timeMap = new Map<string, Record<string, number | string>>();

  for (const [key, points] of Object.entries(sparklines)) {
    for (const point of points as SparklinePoint[]) {
      if (!timeMap.has(point.t)) {
        timeMap.set(point.t, { timestamp: point.t });
      }
      timeMap.get(point.t)![key] = point.v;
    }
  }

  return Array.from(timeMap.values()).sort((a, b) =>
    String(a.timestamp).localeCompare(String(b.timestamp)),
  );
}

export function EntityGrowthChart({ data }: { data: EntitySparklines }) {
  const [active, setActive] = useState<Set<string>>(new Set(["memories"]));

  const series = mergeSeries(data.sparklines);

  function toggle(key: string) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* Metric toggle pills */}
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium mr-1">Growth</h3>
          {METRIC_DEFS.map(({ key, label, color }) => {
            const isActive = active.has(key);
            const total = data.totals[key];
            return (
              <button
                key={key}
                onClick={() => toggle(key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs transition-colors border",
                  isActive
                    ? "border-transparent bg-muted text-foreground"
                    : "border-border/50 text-muted-foreground/60 hover:text-muted-foreground hover:border-border",
                )}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full shrink-0 transition-opacity"
                  style={{
                    background: color,
                    opacity: isActive ? 1 : 0.25,
                  }}
                />
                {label}
                <span className="font-mono tabular-nums">{formatNumber(total)}</span>
              </button>
            );
          })}
        </div>

        {/* Chart */}
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart
            data={series}
            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          >
            <defs>
              {METRIC_DEFS.map(({ key, color }) => (
                <linearGradient
                  key={key}
                  id={`eg-grad-${key}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTick}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelFormatter={(v) =>
                new Date(v).toLocaleDateString(undefined, {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })
              }
            />
            {METRIC_DEFS.filter(({ key }) => active.has(key)).map(
              ({ key, color }) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={color}
                  fill={`url(#eg-grad-${key})`}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              ),
            )}
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
