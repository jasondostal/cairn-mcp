"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type VisualizationPoint } from "@/lib/api";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MultiSelect } from "@/components/ui/multi-select";
import { MemorySheet } from "@/components/memory-sheet";
import { PageLayout } from "@/components/page-layout";

// Deterministic color palette for clusters
const CLUSTER_COLORS = [
  "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#6366f1",
  "#84cc16", "#e11d48", "#0ea5e9", "#d946ef", "#facc15",
];
const NOISE_COLOR = "#6b7280";

function getColor(clusterId: number | null, clusterIds: number[]): string {
  if (clusterId === null) return NOISE_COLOR;
  const idx = clusterIds.indexOf(clusterId);
  return CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
}

const CANVAS_HEIGHT = 500;
const PADDING = 40;
const POINT_RADIUS = 5;

export default function ClusterVisualizationPage() {
  const [points, setPoints] = useState<VisualizationPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<VisualizationPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();
  const [project, setProject] = useState<string[]>([]);
  const { projects } = useProjectSelector();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Zoom/pan state
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  function load(proj?: string[]) {
    const p = proj ?? project;
    setLoading(true);
    setError(null);
    api
      .clusterVisualization({ project: p.length ? p.join(",") : undefined })
      .then((data) => {
        setPoints(data.points);
        // Reset transform on new data
        transformRef.current = { x: 0, y: 0, scale: 1 };
      })
      .catch((err) => setError(err?.message || "Failed to load visualization"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const projectOptions = projects.map((p) => ({ value: p.name, label: p.name }));

  function handleProjectChange(value: string[]) {
    setProject(value);
    load(value);
  }

  // Get unique cluster IDs for consistent color mapping
  const clusterIds = Array.from(
    new Set(points.filter((p) => p.cluster_id !== null).map((p) => p.cluster_id!))
  ).sort();

  // Compute coordinate bounds with padding
  const xMin = points.length ? Math.min(...points.map((p) => p.x)) : 0;
  const xMax = points.length ? Math.max(...points.map((p) => p.x)) : 1;
  const yMin = points.length ? Math.min(...points.map((p) => p.y)) : 0;
  const yMax = points.length ? Math.max(...points.map((p) => p.y)) : 1;
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  const toCanvasCoords = useCallback(
    (x: number, y: number, width: number, height: number) => ({
      cx: PADDING + ((x - xMin) / xRange) * (width - 2 * PADDING),
      cy: PADDING + ((y - yMin) / yRange) * (height - 2 * PADDING),
    }),
    [xMin, xRange, yMin, yRange]
  );

  // Draw the scatter plot
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length === 0) return;

    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = width * dpr;
    canvas.height = CANVAS_HEIGHT * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${CANVAS_HEIGHT}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, CANVAS_HEIGHT);

    const t = transformRef.current;
    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.scale, t.scale);

    // Draw points
    for (const point of points) {
      const { cx, cy } = toCanvasCoords(point.x, point.y, width, CANVAS_HEIGHT);
      const color = getColor(point.cluster_id, clusterIds);

      ctx.beginPath();
      ctx.arc(cx, cy, POINT_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = hoveredPoint?.id === point.id ? 1.0 : 0.7;
      ctx.fill();

      if (hoveredPoint?.id === point.id) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    ctx.globalAlpha = 1.0;
    ctx.restore();
  }, [points, clusterIds, hoveredPoint, toCanvasCoords]);

  function canvasToData(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: clientX, y: clientY };
    const rect = canvas.getBoundingClientRect();
    const t = transformRef.current;
    return {
      x: (clientX - rect.left - t.x) / t.scale,
      y: (clientY - rect.top - t.y) / t.scale,
    };
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas || points.length === 0) return;

    if (isDraggingRef.current) {
      const t = transformRef.current;
      t.x += e.clientX - dragStartRef.current.x;
      t.y += e.clientY - dragStartRef.current.y;
      dragStartRef.current = { x: e.clientX, y: e.clientY };
      // Trigger redraw
      setHoveredPoint((prev) => prev); // force re-render
      return;
    }

    const { x: mx, y: my } = canvasToData(e.clientX, e.clientY);
    const width = canvas.getBoundingClientRect().width;

    let closest: VisualizationPoint | null = null;
    let minDist = Infinity;

    for (const point of points) {
      const { cx, cy } = toCanvasCoords(point.x, point.y, width, CANVAS_HEIGHT);
      const dist = Math.sqrt((mx - cx) ** 2 + (my - cy) ** 2);
      if (dist < 15 && dist < minDist) {
        minDist = dist;
        closest = point;
      }
    }

    setHoveredPoint(closest);
    if (closest) {
      setTooltipPos({ x: e.clientX, y: e.clientY });
    }
  }

  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    isDraggingRef.current = true;
    dragStartRef.current = { x: e.clientX, y: e.clientY };
  }

  function handleMouseUp() {
    isDraggingRef.current = false;
  }

  function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    if (dx * dx + dy * dy > 25) return;
    if (hoveredPoint) openSheet(hoveredPoint.id);
  }

  function handleWheel(e: React.WheelEvent<HTMLCanvasElement>) {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const t = transformRef.current;
    const zoomFactor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.max(0.1, Math.min(5, t.scale * zoomFactor));
    const ratio = newScale / t.scale;

    t.x = mx - ratio * (mx - t.x);
    t.y = my - ratio * (my - t.y);
    t.scale = newScale;

    // Trigger redraw
    setHoveredPoint((prev) => prev);
  }

  // Build legend
  const legendItems = clusterIds.map((id) => ({
    id,
    label: points.find((p) => p.cluster_id === id)?.cluster_label || `Cluster ${id}`,
    color: getColor(id, clusterIds),
  }));
  const hasNoise = points.some((p) => p.cluster_id === null);

  return (
    <PageLayout
      title="Cluster Visualization"
      titleExtra={
        <Button variant="outline" size="sm" onClick={() => window.history.back()}>
          Back to Clusters
        </Button>
      }
      filters={
        <MultiSelect
          options={projectOptions}
          value={project}
          onValueChange={handleProjectChange}
          placeholder="All projects"
          searchPlaceholder="Search projects…"
          maxCount={2}
        />
      }
    >
      {loading && <Skeleton className="h-[500px]" />}

      {error && (
        <ErrorState message="Failed to load visualization" detail={error} />
      )}

      {!loading && !error && points.length === 0 && (
        <div className="flex h-[300px] items-center justify-center rounded-lg border border-border bg-card">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              No memories with embeddings to visualize.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Store some memories first, then come back to see the scatter plot.
            </p>
          </div>
        </div>
      )}

      {!loading && !error && points.length > 0 && (
        <>
          <div
            ref={containerRef}
            className="relative overflow-hidden rounded-lg border border-border bg-card"
          >
            <canvas
              ref={canvasRef}
              onMouseMove={handleMouseMove}
              onMouseDown={handleMouseDown}
              onMouseUp={handleMouseUp}
              onMouseLeave={() => {
                handleMouseUp();
                setHoveredPoint(null);
              }}
              onClick={handleClick}
              onWheel={handleWheel}
              className="w-full cursor-grab active:cursor-grabbing"
              style={{ height: CANVAS_HEIGHT }}
            />

            {/* Tooltip */}
            {hoveredPoint && (
              <div
                className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
                style={{
                  left: tooltipPos.x + 12,
                  top: tooltipPos.y - 8,
                }}
              >
                <p className="font-medium">
                  {hoveredPoint.summary || `Memory #${hoveredPoint.id}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  #{hoveredPoint.id} &middot; {hoveredPoint.memory_type}
                  {hoveredPoint.cluster_label && (
                    <> &middot; {hoveredPoint.cluster_label}</>
                  )}
                </p>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 text-xs">
            {legendItems.map((item) => (
              <div key={item.id} className="flex items-center gap-1.5">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-muted-foreground">{item.label}</span>
              </div>
            ))}
            {hasNoise && (
              <div className="flex items-center gap-1.5">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: NOISE_COLOR }}
                />
                <span className="text-muted-foreground">Unclustered</span>
              </div>
            )}
            <span className="ml-auto text-muted-foreground">
              {points.length} memories
            </span>
          </div>
        </>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
