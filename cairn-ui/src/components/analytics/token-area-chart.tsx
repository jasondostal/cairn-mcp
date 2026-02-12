"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { TimeseriesPoint } from "@/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

function formatTick(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

export function TokenAreaChart({ series }: { series: TimeseriesPoint[] }) {
  if (!series.length) {
    return (
      <Card>
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">No token data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium">Token Usage</h3>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="gradIn" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.4} />
                <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradOut" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--chart-2))" stopOpacity={0.4} />
                <stop offset="100%" stopColor="hsl(var(--chart-2))" stopOpacity={0} />
              </linearGradient>
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
              tickFormatter={formatTokens}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 6,
                fontSize: 12,
              }}
              labelFormatter={(v) => new Date(v).toLocaleString()}
              formatter={(v, name) => [formatTokens(Number(v ?? 0)), name === "tokens_in" ? "Input" : "Output"]}
            />
            <Area
              type="monotone"
              dataKey="tokens_in"
              stackId="1"
              stroke="hsl(var(--chart-1))"
              fill="url(#gradIn)"
              strokeWidth={1.5}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="tokens_out"
              stackId="1"
              stroke="hsl(var(--chart-2))"
              fill="url(#gradOut)"
              strokeWidth={1.5}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: "hsl(var(--chart-1))" }} />
            Input
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: "hsl(var(--chart-2))" }} />
            Output
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
