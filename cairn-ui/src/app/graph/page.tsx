"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { api, type GraphResult } from "@/lib/api";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";

// --- Colors ---

const TYPE_COLORS: Record<string, string> = {
  note: "#3b82f6",
  decision: "#f59e0b",
  rule: "#ef4444",
  "code-snippet": "#22c55e",
  learning: "#8b5cf6",
  research: "#06b6d4",
  discussion: "#ec4899",
  progress: "#14b8a6",
  task: "#f97316",
  debug: "#e11d48",
  design: "#6366f1",
};
const DEFAULT_NODE_COLOR = "#6b7280";

const RELATION_COLORS: Record<string, string> = {
  extends: "#3b82f6",
  contradicts: "#ef4444",
  implements: "#22c55e",
  depends_on: "#f59e0b",
  related: "#6b7280",
};
const DEFAULT_EDGE_COLOR = "#6b7280";

const RELATION_TYPES = ["all", "extends", "contradicts", "implements", "depends_on", "related"] as const;

// --- Simulation types ---

interface SimNode extends SimulationNodeDatum {
  id: number;
  summary: string;
  memory_type: string;
  importance: number;
  project: string;
  radius: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  relation: string;
}

const CANVAS_HEIGHT = 600;

export default function GraphPage() {
  const [data, setData] = useState<GraphResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [relationType, setRelationType] = useState("all");

  // Simulation state
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const simRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);

  // Interaction state
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<SimLink | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  // Zoom/pan state
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const dragNodeRef = useRef<SimNode | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);

  function load() {
    setLoading(true);
    setError(null);
    api
      .graph({
        project: project || undefined,
        relation_type: relationType === "all" ? undefined : relationType,
      })
      .then((result) => {
        setData(result);
        initSimulation(result);
      })
      .catch((err) => setError(err?.message || "Failed to load graph"))
      .finally(() => setLoading(false));
  }

  function initSimulation(result: GraphResult) {
    // Stop previous
    if (simRef.current) simRef.current.stop();
    cancelAnimationFrame(rafRef.current);

    const width = containerRef.current?.clientWidth || 800;

    // Build nodes
    const nodeMap = new Map<number, SimNode>();
    const nodes: SimNode[] = result.nodes.map((n) => {
      const node: SimNode = {
        id: n.id,
        summary: n.summary,
        memory_type: n.memory_type,
        importance: n.importance,
        project: n.project,
        radius: 5 + n.importance * 8,
        x: width / 2 + (Math.random() - 0.5) * 200,
        y: CANVAS_HEIGHT / 2 + (Math.random() - 0.5) * 200,
      };
      nodeMap.set(n.id, node);
      return node;
    });

    // Build links
    const links: SimLink[] = result.edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
        relation: e.relation,
      }));

    nodesRef.current = nodes;
    linksRef.current = links;

    // Reset transform
    transformRef.current = { x: 0, y: 0, scale: 1 };

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(100)
      )
      .force("charge", forceManyBody<SimNode>().strength(-150))
      .force("center", forceCenter(width / 2, CANVAS_HEIGHT / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d) => d.radius + 2)
      )
      .alphaDecay(0.01)
      .on("tick", () => {
        rafRef.current = requestAnimationFrame(draw);
      });

    simRef.current = sim;
  }

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

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

    const nodes = nodesRef.current;
    const links = linksRef.current;
    const hNode = hoveredNode;

    // Connected node IDs for highlighting
    const connectedIds = new Set<number>();
    if (hNode) {
      connectedIds.add(hNode.id);
      for (const link of links) {
        const s = link.source as SimNode;
        const t2 = link.target as SimNode;
        if (s.id === hNode.id) connectedIds.add(t2.id);
        if (t2.id === hNode.id) connectedIds.add(s.id);
      }
    }

    // Draw edges
    for (const link of links) {
      const s = link.source as SimNode;
      const t2 = link.target as SimNode;
      if (s.x == null || s.y == null || t2.x == null || t2.y == null) continue;

      const isHighlighted =
        hNode && (s.id === hNode.id || t2.id === hNode.id);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t2.x, t2.y);
      ctx.strokeStyle = RELATION_COLORS[link.relation] || DEFAULT_EDGE_COLOR;
      ctx.globalAlpha = isHighlighted ? 0.8 : hNode ? 0.08 : 0.3;
      ctx.lineWidth = isHighlighted ? 2 : 1;
      ctx.stroke();
    }

    ctx.globalAlpha = 1.0;

    // Draw nodes
    for (const node of nodes) {
      if (node.x == null || node.y == null) continue;

      const dimmed = hNode && !connectedIds.has(node.id);

      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = TYPE_COLORS[node.memory_type] || DEFAULT_NODE_COLOR;
      ctx.globalAlpha = dimmed ? 0.15 : 0.85;
      ctx.fill();

      // Highlight ring on hover
      if (hNode && node.id === hNode.id) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.globalAlpha = 1;
        ctx.stroke();
      }
    }

    ctx.globalAlpha = 1.0;
    ctx.restore();
  }, [hoveredNode]);

  // Initial load
  useEffect(() => {
    load();
    return () => {
      if (simRef.current) simRef.current.stop();
      cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw when hover state changes
  useEffect(() => {
    rafRef.current = requestAnimationFrame(draw);
  }, [hoveredNode, draw]);

  // --- Canvas to simulation coordinates ---
  function canvasToSim(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const t = transformRef.current;
    return {
      x: (clientX - rect.left - t.x) / t.scale,
      y: (clientY - rect.top - t.y) / t.scale,
    };
  }

  function findNodeAt(sx: number, sy: number): SimNode | null {
    const nodes = nodesRef.current;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.x == null || n.y == null) continue;
      const dx = sx - n.x;
      const dy = sy - n.y;
      if (dx * dx + dy * dy < (n.radius + 4) ** 2) return n;
    }
    return null;
  }

  function findEdgeAt(sx: number, sy: number): SimLink | null {
    const links = linksRef.current;
    for (const link of links) {
      const s = link.source as SimNode;
      const t = link.target as SimNode;
      if (s.x == null || s.y == null || t.x == null || t.y == null) continue;

      // Point-to-line-segment distance
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const lenSq = dx * dx + dy * dy;
      if (lenSq === 0) continue;
      const param = Math.max(0, Math.min(1, ((sx - s.x) * dx + (sy - s.y) * dy) / lenSq));
      const projX = s.x + param * dx;
      const projY = s.y + param * dy;
      const dist = Math.sqrt((sx - projX) ** 2 + (sy - projY) ** 2);
      if (dist < 6) return link;
    }
    return null;
  }

  // --- Event handlers ---

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const { x: sx, y: sy } = canvasToSim(e.clientX, e.clientY);

    if (isDraggingRef.current && dragNodeRef.current) {
      // Dragging a node
      const node = dragNodeRef.current;
      node.fx = sx;
      node.fy = sy;
      simRef.current?.alpha(0.3).restart();
      return;
    }

    if (isDraggingRef.current && !dragNodeRef.current) {
      // Panning
      const t = transformRef.current;
      t.x += e.clientX - dragStartRef.current.x;
      t.y += e.clientY - dragStartRef.current.y;
      dragStartRef.current = { x: e.clientX, y: e.clientY };
      rafRef.current = requestAnimationFrame(draw);
      return;
    }

    // Hover detection
    const node = findNodeAt(sx, sy);
    if (node) {
      setHoveredNode(node);
      setHoveredEdge(null);
      setTooltipPos({ x: e.clientX, y: e.clientY });
    } else {
      const edge = findEdgeAt(sx, sy);
      setHoveredNode(null);
      setHoveredEdge(edge);
      if (edge) setTooltipPos({ x: e.clientX, y: e.clientY });
    }
  }

  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    const { x: sx, y: sy } = canvasToSim(e.clientX, e.clientY);
    const node = findNodeAt(sx, sy);
    isDraggingRef.current = true;
    dragStartRef.current = { x: e.clientX, y: e.clientY };

    if (node) {
      dragNodeRef.current = node;
      node.fx = node.x;
      node.fy = node.y;
      simRef.current?.alphaTarget(0.3).restart();
    }
  }

  function handleMouseUp() {
    isDraggingRef.current = false;
    if (dragNodeRef.current) {
      dragNodeRef.current.fx = null;
      dragNodeRef.current.fy = null;
      dragNodeRef.current = null;
      simRef.current?.alphaTarget(0);
    }
  }

  function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    // Only trigger click if not dragging far
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    if (dx * dx + dy * dy > 25) return;

    const { x: sx, y: sy } = canvasToSim(e.clientX, e.clientY);
    const node = findNodeAt(sx, sy);
    if (node) openSheet(node.id);
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

    rafRef.current = requestAnimationFrame(draw);
  }

  // Connection count per node
  function connectionCount(nodeId: number): number {
    return linksRef.current.filter((l) => {
      const s = l.source as SimNode;
      const t = l.target as SimNode;
      return s.id === nodeId || t.id === nodeId;
    }).length;
  }

  const stats = data?.stats;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Knowledge Graph</h1>
        {stats && (
          <Badge variant="secondary" className="font-mono text-xs">
            {stats.node_count} nodes, {stats.edge_count} edges
          </Badge>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Filter by project"
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="w-48"
        />
        <div className="flex gap-1">
          {RELATION_TYPES.map((rt) => (
            <Button
              key={rt}
              variant={relationType === rt ? "default" : "outline"}
              size="sm"
              onClick={() => setRelationType(rt)}
            >
              {rt === "all" ? "All" : rt.replace("_", " ")}
            </Button>
          ))}
        </div>
        <Button onClick={load}>Apply</Button>
      </div>

      {/* Loading */}
      {loading && <Skeleton className="h-[600px]" />}

      {/* Error */}
      {error && <ErrorState message="Failed to load graph" detail={error} />}

      {/* Empty state */}
      {!loading && !error && data && data.nodes.length === 0 && (
        <div className="flex h-[400px] items-center justify-center rounded-lg border border-border bg-card">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              No relationships found.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Relationships are extracted automatically when memories are stored.
              Try selecting a different project or clearing filters.
            </p>
          </div>
        </div>
      )}

      {/* Graph canvas */}
      {!loading && !error && data && data.nodes.length > 0 && (
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
                setHoveredNode(null);
                setHoveredEdge(null);
              }}
              onClick={handleClick}
              onWheel={handleWheel}
              className="w-full cursor-grab active:cursor-grabbing"
              style={{ height: CANVAS_HEIGHT }}
            />

            {/* Node tooltip */}
            {hoveredNode && (
              <div
                className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
                style={{
                  left: tooltipPos.x + 12,
                  top: tooltipPos.y - 8,
                }}
              >
                <p className="font-medium">{hoveredNode.summary}</p>
                <p className="text-xs text-muted-foreground">
                  #{hoveredNode.id} &middot; {hoveredNode.memory_type} &middot;
                  importance {hoveredNode.importance.toFixed(1)} &middot;{" "}
                  {connectionCount(hoveredNode.id)} connections
                </p>
                {hoveredNode.project && (
                  <p className="text-xs text-muted-foreground">
                    {hoveredNode.project}
                  </p>
                )}
              </div>
            )}

            {/* Edge tooltip */}
            {!hoveredNode && hoveredEdge && (
              <div
                className="pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
                style={{
                  left: tooltipPos.x + 12,
                  top: tooltipPos.y - 8,
                }}
              >
                <p className="text-xs">
                  <span className="font-medium">
                    {hoveredEdge.relation.replace("_", " ")}
                  </span>
                  {" "}
                  #{(hoveredEdge.source as SimNode).id} → #{(hoveredEdge.target as SimNode).id}
                </p>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
            <span className="font-medium text-muted-foreground">Nodes:</span>
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-muted-foreground">{type}</span>
              </div>
            ))}
            <span className="ml-4 font-medium text-muted-foreground">Edges:</span>
            {Object.entries(RELATION_COLORS).map(([rel, color]) => (
              <div key={rel} className="flex items-center gap-1.5">
                <div
                  className="h-0.5 w-4 rounded"
                  style={{ backgroundColor: color }}
                />
                <span className="text-muted-foreground">
                  {rel.replace("_", " ")}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}
