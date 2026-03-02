"use client";

import { useRef, useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { AnalyticsOperation, HeatmapDay } from "@/lib/api";

interface ActivityHeatmapProps {
  /** Pre-aggregated daily counts from /analytics/heatmap endpoint */
  heatmapData?: HeatmapDay[];
  /** Raw operations — used as fallback if heatmapData not provided */
  operations?: AnalyticsOperation[];
}

const GAP = 3;
const MIN_CELL = 4;
const MAX_CELL = 11;

export function ActivityHeatmap({ heatmapData, operations }: ActivityHeatmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Build day counts from either pre-aggregated data or raw operations
  const dayCounts = new Map<string, number>();

  if (heatmapData) {
    for (const d of heatmapData) {
      dayCounts.set(d.date, d.count);
    }
  } else if (operations) {
    for (const op of operations) {
      const d = new Date(op.timestamp);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      dayCounts.set(key, (dayCounts.get(key) ?? 0) + 1);
    }
  }

  // Generate last 365 days
  const days: { key: string; count: number; label: string; dow: number; week: number }[] = [];
  const today = new Date();
  const startDay = new Date(today);
  startDay.setDate(startDay.getDate() - 364);

  // Align to Sunday
  const startDow = startDay.getDay();
  startDay.setDate(startDay.getDate() - startDow);

  for (let i = 0; i <= 371; i++) {
    const d = new Date(startDay);
    d.setDate(d.getDate() + i);
    if (d > today) break;

    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const dow = d.getDay();
    const week = Math.floor(i / 7);
    days.push({
      key,
      count: dayCounts.get(key) ?? 0,
      label: `${d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}: ${dayCounts.get(key) ?? 0} ops`,
      dow,
      week,
    });
  }

  const maxCount = Math.max(1, ...days.map((d) => d.count));
  const totalWeeks = days.length > 0 ? days[days.length - 1].week + 1 : 0;

  // Dynamic cell sizing based on container width
  const rawCell = totalWeeks > 0 && containerWidth > 0
    ? (containerWidth - GAP * (totalWeeks - 1)) / totalWeeks
    : MAX_CELL;
  const cellSize = Math.max(MIN_CELL, Math.min(MAX_CELL, Math.floor(rawCell)));

  function intensity(count: number): string {
    if (count === 0) return "bg-muted/30";
    const ratio = count / maxCount;
    if (ratio < 0.25) return "bg-emerald-900/60";
    if (ratio < 0.5) return "bg-emerald-700/70";
    if (ratio < 0.75) return "bg-emerald-500/80";
    return "bg-emerald-400";
  }

  // Build grid: 7 rows (days) x N cols (weeks)
  const grid: (typeof days[0] | null)[][] = Array.from({ length: 7 }, () =>
    Array.from({ length: totalWeeks }, () => null)
  );
  for (const d of days) {
    grid[d.dow][d.week] = d;
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <h3 className="text-sm font-medium">Activity</h3>
        <div ref={containerRef}>
          {containerWidth > 0 && (
            <div
              className="inline-grid"
              style={{
                gridTemplateColumns: `repeat(${totalWeeks}, ${cellSize}px)`,
                gridTemplateRows: `repeat(7, ${cellSize}px)`,
                gap: `${GAP}px`,
              }}
            >
              {grid.flat().map((cell, i) =>
                cell ? (
                  <div
                    key={cell.key}
                    title={cell.label}
                    className={`rounded-sm ${intensity(cell.count)} transition-colors`}
                  />
                ) : (
                  <div key={`empty-${i}`} />
                )
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span>Less</span>
          {["bg-muted/30", "bg-emerald-900/60", "bg-emerald-700/70", "bg-emerald-500/80", "bg-emerald-400"].map((c) => (
            <div
              key={c}
              className={`rounded-sm ${c}`}
              style={{ height: Math.max(8, cellSize - 1), width: Math.max(8, cellSize - 1) }}
            />
          ))}
          <span>More</span>
        </div>
      </CardContent>
    </Card>
  );
}
