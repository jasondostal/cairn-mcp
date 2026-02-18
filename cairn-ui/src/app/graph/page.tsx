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
import { api, type KnowledgeGraphResult } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { PageLayout } from "@/components/page-layout";

// --- Entity type colors ---

const ENTITY_COLORS: Record<string, string> = {
  Person: "#f59e0b",
  Organization: "#ef4444",
  Place: "#22c55e",
  Event: "#ec4899",
  Project: "#3b82f6",
  Task: "#f97316",
  Technology: "#8b5cf6",
  Product: "#06b6d4",
  Concept: "#6b7280",
};
const DEFAULT_NODE_COLOR = "#6b7280";

// --- Aspect colors for edges ---
const ASPECT_COLORS: Record<string, string> = {
  Identity: "#f59e0b",
  Knowledge: "#3b82f6",
  Belief: "#8b5cf6",
  Preference: "#ec4899",
  Action: "#22c55e",
  Goal: "#14b8a6",
  Directive: "#ef4444",
  Decision: "#f97316",
  Event: "#06b6d4",
  Problem: "#e11d48",
  Relationship: "#6366f1",
};
const DEFAULT_EDGE_COLOR = "#475569";

const ENTITY_TYPES = [
  "all",
  "Person",
  "Project",
  "Technology",
  "Concept",
  "Event",
  "Organization",
  "Place",
  "Product",
  "Task",
] as const;

// --- Simulation types ---

interface SimNode extends SimulationNodeDatum {
  id: string; // uuid
  name: string;
  entity_type: string;
  project_id: number;
  stmt_count: number;
  radius: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  predicate: string;
  fact: string;
  aspect: string;
}

const CANVAS_HEIGHT = 600;

export default function GraphPage() {
  const [data, setData] = useState<KnowledgeGraphResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  // Simulation state
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const simRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);

  // Interaction state
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<SimLink | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);

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
      .knowledgeGraph({
        project: project || undefined,
        entity_type: entityTypeFilter === "all" ? undefined : entityTypeFilter,
      })
      .then((result) => {
        setData(result);
        initSimulation(result);
      })
      .catch((err) => setError(err?.message || "Failed to load knowledge graph"))
      .finally(() => setLoading(false));
  }

  function initSimulation(result: KnowledgeGraphResult) {
    if (simRef.current) simRef.current.stop();
    cancelAnimationFrame(rafRef.current);

    const width = containerRef.current?.clientWidth || 800;

    // Build nodes
    const nodeMap = new Map<string, SimNode>();
    const nodes: SimNode[] = result.nodes.map((n) => {
      const radius = Math.max(5, Math.min(20, 4 + Math.sqrt(n.stmt_count) * 3));
      const node: SimNode = {
        id: n.uuid,
        name: n.name,
        entity_type: n.entity_type,
        project_id: n.project_id,
        stmt_count: n.stmt_count,
        radius,
        x: width / 2 + (Math.random() - 0.5) * 300,
        y: CANVAS_HEIGHT / 2 + (Math.random() - 0.5) * 300,
      };
      nodeMap.set(n.uuid, node);
      return node;
    });

    // Build links — only where both endpoints exist
    const links: SimLink[] = result.edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
        predicate: e.predicate,
        fact: e.fact,
        aspect: e.aspect,
      }));

    nodesRef.current = nodes;
    linksRef.current = links;

    transformRef.current = { x: 0, y: 0, scale: 1 };

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(120)
      )
      .force("charge", forceManyBody<SimNode>().strength(-200))
      .force("center", forceCenter(width / 2, CANVAS_HEIGHT / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d) => d.radius + 4)
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
    const sNode = selectedNode;
    const activeNode = hNode || sNode;

    // Connected node IDs for highlighting
    const connectedIds = new Set<string>();
    if (activeNode) {
      connectedIds.add(activeNode.id);
      for (const link of links) {
        const s = link.source as SimNode;
        const tgt = link.target as SimNode;
        if (s.id === activeNode.id) connectedIds.add(tgt.id);
        if (tgt.id === activeNode.id) connectedIds.add(s.id);
      }
    }

    // Search highlighting
    const searchLower = searchTerm.toLowerCase();
    const isSearching = searchLower.length > 0;
    const matchesSearch = (n: SimNode) =>
      n.name.toLowerCase().includes(searchLower);

    // Draw edges
    for (const link of links) {
      const s = link.source as SimNode;
      const tgt = link.target as SimNode;
      if (s.x == null || s.y == null || tgt.x == null || tgt.y == null)
        continue;

      const isHighlighted =
        activeNode && (s.id === activeNode.id || tgt.id === activeNode.id);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = ASPECT_COLORS[link.aspect] || DEFAULT_EDGE_COLOR;
      ctx.globalAlpha = isHighlighted ? 0.8 : activeNode ? 0.06 : 0.2;
      ctx.lineWidth = isHighlighted ? 2 : 0.5;
      ctx.stroke();

      // Draw predicate label on highlighted edges
      if (isHighlighted && t.scale > 0.6) {
        const mx = (s.x + tgt.x) / 2;
        const my = (s.y + tgt.y) / 2;
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = "#94a3b8";
        ctx.font = `${10 / t.scale}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(link.predicate, mx, my - 4);
      }
    }

    ctx.globalAlpha = 1.0;

    // Draw nodes
    for (const node of nodes) {
      if (node.x == null || node.y == null) continue;

      const dimmed = activeNode
        ? !connectedIds.has(node.id)
        : isSearching
        ? !matchesSearch(node)
        : false;

      const fillColor = ENTITY_COLORS[node.entity_type] || DEFAULT_NODE_COLOR;
      const alpha = dimmed ? 0.1 : 0.85;

      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = fillColor;
      ctx.globalAlpha = alpha;
      ctx.fill();

      // Highlight ring
      if (activeNode && node.id === activeNode.id) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2.5;
        ctx.globalAlpha = 1;
        ctx.stroke();
      }

      // Draw labels at higher zoom or for large nodes
      if (
        !dimmed &&
        (t.scale > 0.8 || node.stmt_count > 10)
      ) {
        ctx.globalAlpha = dimmed ? 0.1 : 0.9;
        ctx.fillStyle = "#e2e8f0";
        const fontSize = Math.max(9, Math.min(13, node.radius * 0.9));
        ctx.font = `${fontSize / t.scale}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(
          node.name.length > 20 ? node.name.slice(0, 18) + "..." : node.name,
          node.x,
          node.y + node.radius + 12 / t.scale
        );
      }
    }

    ctx.globalAlpha = 1.0;
    ctx.restore();
  }, [hoveredNode, selectedNode, searchTerm]);

  // Initial load
  useEffect(() => {
    load();
    return () => {
      if (simRef.current) simRef.current.stop();
      cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw on state changes
  useEffect(() => {
    rafRef.current = requestAnimationFrame(draw);
  }, [hoveredNode, selectedNode, draw, searchTerm]);

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
      const tgt = link.target as SimNode;
      if (s.x == null || s.y == null || tgt.x == null || tgt.y == null)
        continue;
      const dx = tgt.x - s.x;
      const dy = tgt.y - s.y;
      const lenSq = dx * dx + dy * dy;
      if (lenSq === 0) continue;
      const param = Math.max(
        0,
        Math.min(1, ((sx - s.x) * dx + (sy - s.y) * dy) / lenSq)
      );
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
      const node = dragNodeRef.current;
      node.fx = sx;
      node.fy = sy;
      simRef.current?.alpha(0.3).restart();
      return;
    }

    if (isDraggingRef.current && !dragNodeRef.current) {
      const t = transformRef.current;
      t.x += e.clientX - dragStartRef.current.x;
      t.y += e.clientY - dragStartRef.current.y;
      dragStartRef.current = { x: e.clientX, y: e.clientY };
      rafRef.current = requestAnimationFrame(draw);
      return;
    }

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
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    if (dx * dx + dy * dy > 25) return;

    const { x: sx, y: sy } = canvasToSim(e.clientX, e.clientY);
    const node = findNodeAt(sx, sy);
    setSelectedNode(node === selectedNode ? null : node);
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

  function connectionCount(nodeId: string): number {
    return linksRef.current.filter((l) => {
      const s = l.source as SimNode;
      const tgt = l.target as SimNode;
      return s.id === nodeId || tgt.id === nodeId;
    }).length;
  }

  // Connections for selected node
  const selectedConnections = selectedNode
    ? linksRef.current
        .filter((l) => {
          const s = l.source as SimNode;
          const tgt = l.target as SimNode;
          return s.id === selectedNode.id || tgt.id === selectedNode.id;
        })
        .map((l) => {
          const s = l.source as SimNode;
          const tgt = l.target as SimNode;
          const other = s.id === selectedNode.id ? tgt : s;
          const direction = s.id === selectedNode.id ? "out" : "in";
          return { other, predicate: l.predicate, fact: l.fact, aspect: l.aspect, direction };
        })
    : [];

  const stats = data?.stats;

  return (
    <PageLayout
      title="Knowledge Graph"
      titleExtra={
        stats && (
          <Badge variant="secondary" className="font-mono text-xs">
            {stats.node_count} entities, {stats.edge_count} relationships
          </Badge>
        )
      }
      filters={
        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="Search entities..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-48"
          />
          <Input
            placeholder="Filter by project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            className="w-40"
          />
          <div className="flex gap-1 overflow-x-auto">
            {ENTITY_TYPES.map((et) => (
              <Button
                key={et}
                variant={entityTypeFilter === et ? "default" : "outline"}
                size="sm"
                onClick={() => setEntityTypeFilter(et)}
                className="whitespace-nowrap"
              >
                {et === "all" ? "All" : et}
              </Button>
            ))}
          </div>
          <Button onClick={load}>Apply</Button>
        </div>
      }
    >
      {loading && <Skeleton className="h-[600px]" />}

      {error && <ErrorState message="Failed to load knowledge graph" detail={error} />}

      {!loading && !error && data && data.nodes.length === 0 && (
        <div className="flex h-[400px] items-center justify-center rounded-lg border border-border bg-card">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              No entities found in the knowledge graph.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Knowledge extraction runs automatically when memories are stored
              (requires Neo4j + knowledge_extraction enabled).
            </p>
          </div>
        </div>
      )}

      {!loading && !error && data && data.nodes.length > 0 && (
        <div className="flex gap-4">
          {/* Graph canvas */}
          <div className="flex-1">
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
                  <p className="font-medium">{hoveredNode.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {hoveredNode.entity_type} &middot;{" "}
                    {hoveredNode.stmt_count} statements &middot;{" "}
                    {connectionCount(hoveredNode.id)} connections
                  </p>
                </div>
              )}

              {/* Edge tooltip */}
              {!hoveredNode && hoveredEdge && (
                <div
                  className="pointer-events-none fixed z-50 max-w-sm rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
                  style={{
                    left: tooltipPos.x + 12,
                    top: tooltipPos.y - 8,
                  }}
                >
                  <p className="font-medium">{hoveredEdge.predicate}</p>
                  <p className="text-xs text-muted-foreground">{hoveredEdge.fact}</p>
                  <p className="text-xs text-muted-foreground/60">
                    {hoveredEdge.aspect}
                  </p>
                </div>
              )}
            </div>

            {/* Legend */}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {Object.entries(ENTITY_COLORS).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1.5">
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-muted-foreground">{type}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Side panel — selected entity details */}
          {selectedNode && (
            <div className="w-72 shrink-0 space-y-3 rounded-lg border border-border bg-card p-4">
              <div>
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{
                      backgroundColor:
                        ENTITY_COLORS[selectedNode.entity_type] ||
                        DEFAULT_NODE_COLOR,
                    }}
                  />
                  <h3 className="font-semibold text-sm">{selectedNode.name}</h3>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {selectedNode.entity_type} &middot;{" "}
                  {selectedNode.stmt_count} statements &middot;{" "}
                  {connectionCount(selectedNode.id)} connections
                </p>
              </div>

              {selectedConnections.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-muted-foreground mb-2">
                    Relationships ({selectedConnections.length})
                  </h4>
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {selectedConnections.map((conn, i) => (
                      <div
                        key={i}
                        className="rounded border border-border/50 p-2 text-xs cursor-pointer hover:bg-accent/50"
                        onClick={() => setSelectedNode(conn.other)}
                      >
                        <div className="flex items-center gap-1">
                          <span className="text-muted-foreground">
                            {conn.direction === "out" ? "→" : "←"}
                          </span>
                          <span className="font-medium">{conn.predicate}</span>
                          <span className="text-muted-foreground">
                            {conn.direction === "out" ? "→" : "←"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-1">
                          <div
                            className="h-2 w-2 rounded-full shrink-0"
                            style={{
                              backgroundColor:
                                ENTITY_COLORS[conn.other.entity_type] ||
                                DEFAULT_NODE_COLOR,
                            }}
                          />
                          <span>{conn.other.name}</span>
                        </div>
                        <p className="text-muted-foreground/70 mt-0.5 line-clamp-2">
                          {conn.fact}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setSelectedNode(null)}
              >
                Close
              </Button>
            </div>
          )}
        </div>
      )}
    </PageLayout>
  );
}
