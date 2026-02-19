"use client";

import { useMemo } from "react";
import { useLocalStorage } from "@/lib/use-local-storage";
import { Card, CardContent } from "@/components/ui/card";
import { MultiSelect, type MultiSelectOption } from "@/components/ui/multi-select";
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
import {
  Database,
  FolderOpen,
  Network,
  Kanban,
  ListTodo,
  Brain,
  MessageCircle,
  Mail,
} from "lucide-react";

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "oklch(0.696 0.17 162)",   // teal
  "oklch(0.769 0.188 70)",   // gold
  "oklch(0.627 0.265 304)",  // magenta
];

/** Display labels, icons, and sort order for known entity keys. */
const ENTITY_META: Record<string, {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  order: number;
}> = {
  memories:      { label: "Memories",      icon: Database,       order: 0 },
  projects:      { label: "Projects",      icon: FolderOpen,     order: 1 },
  clusters:      { label: "Clusters",      icon: Network,        order: 2 },
  work_items:    { label: "Work Items",    icon: Kanban,         order: 3 },
  tasks:         { label: "Tasks",         icon: ListTodo,       order: 4 },
  thinking:      { label: "Thinking",      icon: Brain,          order: 5 },
  conversations: { label: "Conversations", icon: MessageCircle,  order: 6 },
  messages:      { label: "Messages",      icon: Mail,           order: 7 },
};

function entityLabel(key: string): string {
  return ENTITY_META[key]?.label ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function entityOrder(key: string): number {
  return ENTITY_META[key]?.order ?? 99;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function formatTick(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Merge per-metric sparklines into a unified time series for Recharts.
 *  Fills zeros for timestamps where an entity has no data yet so lines
 *  rise smoothly from the baseline instead of starting abruptly mid-chart. */
function mergeSeries(
  sparklines: Record<string, SparklinePoint[]>,
  activeKeys: string[],
): Record<string, number | string>[] {
  // Collect all unique timestamps across active keys
  const allTimestamps = new Set<string>();
  for (const key of activeKeys) {
    const points = sparklines[key];
    if (!points) continue;
    for (const point of points) allTimestamps.add(point.t);
  }

  // Build sorted timestamp list
  const sorted = Array.from(allTimestamps).sort();

  // Build rows with zero-fill for missing entries
  return sorted.map((t) => {
    const row: Record<string, number | string> = { timestamp: t };
    for (const key of activeKeys) {
      const points = sparklines[key];
      const match = points?.find((p) => p.t === t);
      row[key] = match ? match.v : 0;
    }
    return row;
  });
}

export function EntityGrowthChart({ data }: { data: EntitySparklines }) {
  // Build sorted list of available entity keys from API response
  const entityKeys = useMemo(
    () =>
      Object.keys(data.totals).sort(
        (a, b) => entityOrder(a) - entityOrder(b),
      ),
    [data.totals],
  );

  const [active, setActive] = useLocalStorage<string[]>("cairn-dashboard-entities", ["memories"]);

  // Assign stable colors per key based on entity order
  function colorFor(key: string): string {
    const idx = entityKeys.indexOf(key);
    return CHART_COLORS[idx % CHART_COLORS.length];
  }

  // Options for multi-select — with icons and chart-matched colors
  const options: MultiSelectOption[] = useMemo(
    () =>
      entityKeys.map((key) => ({
        value: key,
        label: `${entityLabel(key)} (${formatNumber(data.totals[key])})`,
        icon: ENTITY_META[key]?.icon,
        color: colorFor(key),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [entityKeys, data.totals],
  );

  const series = useMemo(
    () => mergeSeries(data.sparklines, active),
    [data.sparklines, active],
  );

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* Header + metric selector */}
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium mr-1">Growth</h3>
          <MultiSelect
            options={options}
            value={active}
            onValueChange={(v) => setActive(v.length > 0 ? v : ["memories"])}
            placeholder="Select metrics…"
            searchPlaceholder="Filter entities…"
            maxCount={3}
          />
        </div>

        {/* Chart */}
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart
            data={series}
            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          >
            <defs>
              {active.map((key) => {
                const color = colorFor(key);
                return (
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
                );
              })}
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
            {active.map((key) => {
              const color = colorFor(key);
              return (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={entityLabel(key)}
                  stroke={color}
                  fill={`url(#eg-grad-${key})`}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              );
            })}
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
