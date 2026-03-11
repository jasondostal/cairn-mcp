"use client";

import { useMemo } from "react";
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import type { MetricsBucket } from "@/lib/api";

// ---------------------------------------------------------------------------
// Metric config
// ---------------------------------------------------------------------------

interface MetricLane {
  key: keyof MetricsBucket;
  label: string;
  color: string;
  format: (v: number) => string;
}

const LANES: MetricLane[] = [
  {
    key: "ops_count",
    label: "Ops/sec",
    color: "var(--pulse-ops)",
    format: (v) => v.toString(),
  },
  {
    key: "latency_avg_ms",
    label: "Latency",
    color: "var(--pulse-latency)",
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`),
  },
  {
    key: "tokens_in",
    label: "Tokens in",
    color: "var(--pulse-tokens)",
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toString()),
  },
  {
    key: "errors",
    label: "Errors",
    color: "var(--pulse-errors)",
    format: (v) => v.toString(),
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function trend(buckets: MetricsBucket[], key: keyof MetricsBucket): "up" | "down" | "flat" {
  if (buckets.length < 10) return "flat";
  const recent = buckets.slice(-5);
  const prior = buckets.slice(-10, -5);
  const avg = (arr: MetricsBucket[]) =>
    arr.reduce((sum, b) => sum + (b[key] as number), 0) / arr.length;
  const diff = avg(recent) - avg(prior);
  if (Math.abs(diff) < 0.5) return "flat";
  return diff > 0 ? "up" : "down";
}

const CATEGORY_COLORS: Record<string, string> = {
  reads: "var(--pulse-tokens)",
  writes: "var(--pulse-ops)",
  llm: "var(--pulse-sessions)",
  embedding: "var(--pulse-latency)",
  work: "var(--pulse-errors)",
  sessions: "var(--pulse-sessions)",
  system: "var(--muted-foreground)",
  other: "var(--muted-foreground)",
};

const TREND_ICON: Record<string, string> = { up: "↑", down: "↓", flat: "→" };
const TREND_COLOR: Record<string, string> = {
  up: "text-[var(--pulse-ops)]",
  down: "text-[var(--pulse-errors)]",
  flat: "text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function PulseTooltip({ active, payload }: { active?: boolean; payload?: Array<{ value: number; dataKey: string }> }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md bg-popover border border-border px-2 py-1 text-xs shadow-md">
      {payload.map((p) => {
        const lane = LANES.find((l) => l.key === p.dataKey);
        return (
          <div key={p.dataKey} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: lane?.color }} />
            <span className="text-muted-foreground">{lane?.label}:</span>
            <span className="font-mono tabular-nums">{lane?.format(p.value) ?? p.value}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Idle heartbeat trace
// ---------------------------------------------------------------------------

const EKG_PATH =
  "M0,12 L18,12 L22,10.5 L26,12 L58,12 L62,10 L66,12 L100,12 " +
  "L118,12 L122,10.5 L126,12 L158,12 L162,10 L166,12 L200,12";

function IdleHeartbeat() {
  return (
    <div className="w-full h-full flex items-center overflow-hidden">
      <svg
        viewBox="0 0 200 24"
        preserveAspectRatio="none"
        style={{
          width: "200%",
          height: "60%",
          animation: "ekg-scroll 4s linear infinite",
        }}
      >
        <path
          d={EKG_PATH}
          stroke="var(--pulse-ops)"
          fill="none"
          strokeWidth="1"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.2}
        />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LivePulse() {
  const { buckets, latest, connected } = useMetricsStream();

  const idle = useMemo(
    () =>
      !buckets.length ||
      buckets.every(
        (b) => b.ops_count === 0 && b.latency_avg_ms === 0 && b.tokens_in === 0 && b.errors === 0,
      ),
    [buckets],
  );

  const chartData = useMemo(
    () =>
      buckets.map((b) => ({
        t: formatTime(b.timestamp),
        ops_count: b.ops_count,
        latency_avg_ms: b.latency_avg_ms,
        tokens_in: b.tokens_in,
        errors: b.errors,
      })),
    [buckets],
  );

  return (
    <Card className="h-full">
      <CardContent className="p-4 h-full flex flex-col">
        {/* Header strip */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div
              className={`h-2 w-2 rounded-full shrink-0 ${
                connected
                  ? (latest?.errors ?? 0) > 0
                    ? "bg-[var(--pulse-errors)] animate-pulse"
                    : idle
                      ? "bg-[var(--pulse-ops)]/30 animate-pulse [animation-duration:3s]"
                      : "bg-[var(--pulse-ops)]"
                  : "bg-muted-foreground/40"
              }`}
            />
            <span className="text-xs text-muted-foreground">
              {connected ? "Live" : "Disconnected"}
            </span>
          </div>
          {latest && (
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {formatTime(latest.timestamp)}
            </span>
          )}
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          {LANES.map((lane) => {
            const value = latest ? (latest[lane.key] as number) : 0;
            const t = trend(buckets, lane.key);
            return (
              <div key={lane.key} className="text-center">
                <div className="text-[10px] text-muted-foreground">{lane.label}</div>
                <div className="flex items-center justify-center gap-1">
                  <span className="text-lg font-semibold tabular-nums">
                    {lane.format(value)}
                  </span>
                  <span className={`text-xs ${lane.key === "errors" ? (t === "up" ? TREND_COLOR.up : TREND_COLOR.flat) : (t === "up" ? TREND_COLOR.up : t === "down" ? TREND_COLOR.down : TREND_COLOR.flat)}`}>
                    {TREND_ICON[t]}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Main chart */}
        <div className="flex-1 min-h-0" style={{ minHeight: 80 }}>
          {idle ? (
            <IdleHeartbeat />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  {LANES.map((lane) => (
                    <linearGradient
                      key={lane.key}
                      id={`lp-grad-${lane.key}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor={lane.color} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={lane.color} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <XAxis
                  dataKey="t"
                  tick={{ fontSize: 9, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                  minTickGap={60}
                />
                <YAxis hide />
                <Tooltip
                  content={<PulseTooltip />}
                  cursor={{ stroke: "var(--border)", strokeDasharray: "3 3" }}
                />
                {LANES.map((lane) => (
                  <Area
                    key={lane.key}
                    type="monotone"
                    dataKey={lane.key}
                    stroke={lane.color}
                    strokeWidth={1.5}
                    fill={`url(#lp-grad-${lane.key})`}
                    isAnimationActive={false}
                    dot={false}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Category + tool breakdown */}
        {latest && (Object.keys(latest.by_category ?? {}).length > 0 || Object.keys(latest.by_tool).length > 0) && (
          <div className="mt-2 pt-2 border-t border-border space-y-1">
            {Object.keys(latest.by_category ?? {}).length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {Object.entries(latest.by_category)
                  .sort(([, a], [, b]) => b - a)
                  .map(([cat, count]) => (
                    <span key={cat} className="text-[10px] tabular-nums flex items-center gap-1">
                      <span
                        className="h-1.5 w-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: CATEGORY_COLORS[cat] ?? "var(--muted-foreground)" }}
                      />
                      <span className="font-medium text-foreground">{count}</span>{" "}
                      <span className="text-muted-foreground">{cat}</span>
                    </span>
                  ))}
              </div>
            )}
            {Object.keys(latest.by_tool).length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {Object.entries(latest.by_tool)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 6)
                  .map(([tool, count]) => (
                    <span key={tool} className="text-[10px] text-muted-foreground tabular-nums">
                      <span className="font-medium text-foreground">{count}</span>{" "}
                      {tool}
                    </span>
                  ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
