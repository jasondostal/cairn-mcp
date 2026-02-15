"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { EntitySparklines, SparklinePoint } from "@/lib/api";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { Database, FolderOpen, Network } from "lucide-react";

function MiniSparkline({ data, color }: { data: SparklinePoint[]; color: string }) {
  if (!data.length) return <div className="h-[36px]" />;
  return (
    <ResponsiveContainer width="100%" height={36}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`kpi-grad-${color.replace(/[^a-z0-9]/gi, "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#kpi-grad-${color.replace(/[^a-z0-9]/gi, "")})`}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function getDelta(sparkline: SparklinePoint[]): number | null {
  if (sparkline.length < 2) return null;
  const recent = sparkline.slice(-7);
  return recent.reduce((sum, p) => sum + p.v, 0);
}

interface KpiDef {
  key: keyof EntitySparklines["totals"];
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

const KPI_DEFS: KpiDef[] = [
  { key: "memories", label: "Memories", icon: Database, color: "var(--chart-1)" },
  { key: "projects", label: "Projects", icon: FolderOpen, color: "var(--chart-3)" },
  { key: "clusters", label: "Clusters", icon: Network, color: "var(--chart-4)" },
];

export function SparklineKpiStrip({ data }: { data: EntitySparklines }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {KPI_DEFS.map(({ key, label, icon: Icon, color }) => {
        const total = data.totals[key];
        const sparkline = data.sparklines[key];
        const delta = getDelta(sparkline);

        return (
          <Card key={key}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">{label}</span>
                </div>
                {delta !== null && delta > 0 && (
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    +{delta}
                  </Badge>
                )}
              </div>
              <p className="text-2xl font-semibold tabular-nums mb-1">
                {formatNumber(total)}
              </p>
              <MiniSparkline data={sparkline} color={color} />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
