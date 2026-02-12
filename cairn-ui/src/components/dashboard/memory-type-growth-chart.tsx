"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { MemoryGrowthResult } from "@/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

const CHART_COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
];

function formatTick(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MemoryTypeGrowthChart({ data }: { data: MemoryGrowthResult }) {
  if (!data.series.length) {
    return (
      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">No memory growth data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium">Memory Type Growth</h3>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={data.series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              {data.types.map((type, i) => (
                <linearGradient key={type} id={`mg-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTick}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelFormatter={(v) => new Date(v).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
            />
            {data.types.map((type, i) => (
              <Area
                key={type}
                type="monotone"
                dataKey={type}
                stackId="1"
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                fill={`url(#mg-grad-${i})`}
                strokeWidth={1.5}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          {data.types.map((type, i) => (
            <span key={type} className="flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm"
                style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
              />
              {type}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
