"use client";

import { useCallback, useEffect, useRef } from "react";
import { ProjectPill } from "@/components/project-pill";
import type { forceSimulation } from "d3-force";
import {
  type GraphMode,
  type SimNode,
  type SimLink,
  CANVAS_HEIGHT,
  ENTITY_COLORS,
  ASPECT_COLORS,
  TYPE_COLORS,
  RELATION_COLORS,
  CLUSTER_PALETTE,
  CLUSTER_UNASSIGNED_COLOR,
  DEFAULT_NODE_COLOR,
  DEFAULT_EDGE_COLOR,
} from "./graph-types";

// ────────────────────────────────────────────────────
// Props
// ────────────────────────────────────────────────────

interface GraphCanvasProps {
  mode: GraphMode;
  colorMode: "type" | "cluster";
  searchTerm: string;
  nodesRef: React.RefObject<SimNode[]>;
  linksRef: React.RefObject<SimLink[]>;
  simRef: React.RefObject<ReturnType<typeof forceSimulation<SimNode>> | null>;
  transformRef: React.RefObject<{ x: number; y: number; scale: number }>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  /** Mutable ref the canvas populates with its draw-request function so the simulation tick can trigger redraws */
  drawRequestRef: React.MutableRefObject<(() => void) | null>;
  hoveredNode: SimNode | null;
  hoveredEdge: SimLink | null;
  selectedNode: SimNode | null;
  tooltipPos: { x: number; y: number };
  onHoveredNodeChange: (node: SimNode | null) => void;
  onHoveredEdgeChange: (edge: SimLink | null) => void;
  onTooltipPosChange: (pos: { x: number; y: number }) => void;
  onNodeClick: (node: SimNode | null) => void;
  connectionCount: (nodeId: string) => number;
}

// ────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────

export function GraphCanvas({
  mode,
  colorMode,
  searchTerm,
  nodesRef,
  linksRef,
  simRef,
  transformRef,
  containerRef,
  canvasRef,
  drawRequestRef,
  hoveredNode,
  hoveredEdge,
  selectedNode,
  tooltipPos,
  onHoveredNodeChange,
  onHoveredEdgeChange,
  onTooltipPosChange,
  onNodeClick,
  connectionCount,
}: GraphCanvasProps) {
  const rafRef = useRef<number>(0);
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const dragNodeRef = useRef<SimNode | null>(null);
  const pinchDistRef = useRef(0);
  const touchStartRef = useRef({ x: 0, y: 0 });

  // ────────────────────────────────────────────────
  // Draw
  // ────────────────────────────────────────────────

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
      connectedIds.add(activeNode.nodeId);
      for (const link of links) {
        const s = link.source as SimNode;
        const tgt = link.target as SimNode;
        if (s.nodeId === activeNode.nodeId) connectedIds.add(tgt.nodeId);
        if (tgt.nodeId === activeNode.nodeId) connectedIds.add(s.nodeId);
      }
    }

    // Search highlighting (Neo4j mode only)
    const searchLower = searchTerm.toLowerCase();
    const isSearching = mode === "neo4j" && searchLower.length > 0;
    const matchesSearch = (n: SimNode) =>
      n.label.toLowerCase().includes(searchLower);

    // ── Draw edges ──
    for (const link of links) {
      const s = link.source as SimNode;
      const tgt = link.target as SimNode;
      if (s.x == null || s.y == null || tgt.x == null || tgt.y == null) continue;

      const isHighlighted =
        activeNode && (s.nodeId === activeNode.nodeId || tgt.nodeId === activeNode.nodeId);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tgt.x, tgt.y);

      // Edge color
      if (link.edgeMeta.kind === "neo4j") {
        ctx.strokeStyle = ASPECT_COLORS[link.edgeMeta.aspect] || DEFAULT_EDGE_COLOR;
      } else {
        ctx.strokeStyle = RELATION_COLORS[link.edgeMeta.relation] || DEFAULT_EDGE_COLOR;
      }

      ctx.globalAlpha = isHighlighted ? 0.8 : activeNode ? 0.06 : mode === "neo4j" ? 0.2 : 0.3;
      ctx.lineWidth = isHighlighted ? 2 : mode === "neo4j" ? 0.5 : 1;
      ctx.stroke();

      // Draw predicate label on highlighted edges (Neo4j mode)
      if (isHighlighted && mode === "neo4j" && t.scale > 0.6) {
        const mx = (s.x + tgt.x) / 2;
        const my = (s.y + tgt.y) / 2;
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = "#94a3b8";
        ctx.font = `${10 / t.scale}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(link.edgeLabel, mx, my - 4);
      }
    }

    ctx.globalAlpha = 1.0;

    // ── Draw nodes ──
    for (const node of nodes) {
      if (node.x == null || node.y == null) continue;

      const dimmed = activeNode
        ? !connectedIds.has(node.nodeId)
        : isSearching
        ? !matchesSearch(node)
        : false;

      // Node color
      let fillColor: string;
      if (node.meta.kind === "neo4j") {
        fillColor = ENTITY_COLORS[node.meta.entity_type] || DEFAULT_NODE_COLOR;
      } else if (colorMode === "cluster") {
        if (node.meta.cluster_id != null) {
          fillColor = CLUSTER_PALETTE[node.meta.cluster_id % CLUSTER_PALETTE.length];
        } else {
          fillColor = CLUSTER_UNASSIGNED_COLOR;
        }
      } else {
        fillColor = TYPE_COLORS[node.meta.memory_type] || DEFAULT_NODE_COLOR;
      }

      const alpha = dimmed ? 0.1 : 0.85;

      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = fillColor;
      ctx.globalAlpha = alpha;
      ctx.fill();

      // Highlight ring
      if (activeNode && node.nodeId === activeNode.nodeId) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2.5;
        ctx.globalAlpha = 1;
        ctx.stroke();
      }

      // Labels (Neo4j: at zoom or for large nodes; Postgres: no labels to keep clean)
      if (
        node.meta.kind === "neo4j" &&
        !dimmed &&
        (t.scale > 0.8 || node.meta.stmt_count > 10)
      ) {
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = "#e2e8f0";
        const fontSize = Math.max(9, Math.min(13, node.radius * 0.9));
        ctx.font = `${fontSize / t.scale}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(
          node.label.length > 20 ? node.label.slice(0, 18) + "..." : node.label,
          node.x,
          node.y + node.radius + 12 / t.scale,
        );
      }
    }

    ctx.globalAlpha = 1.0;
    ctx.restore();
  }, [hoveredNode, selectedNode, searchTerm, mode, colorMode, canvasRef, containerRef, transformRef, nodesRef, linksRef]);

  // ────────────────────────────────────────────────
  // Expose draw to the simulation tick via drawRequestRef
  // ────────────────────────────────────────────────

  useEffect(() => {
    drawRequestRef.current = () => {
      rafRef.current = requestAnimationFrame(draw);
    };
    return () => {
      drawRequestRef.current = null;
      cancelAnimationFrame(rafRef.current);
    };
  }, [draw, drawRequestRef]);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(draw);
  }, [hoveredNode, selectedNode, draw, searchTerm, colorMode]);

  // ────────────────────────────────────────────────
  // Canvas ↔ simulation coordinate helpers
  // ────────────────────────────────────────────────

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
      if (s.x == null || s.y == null || tgt.x == null || tgt.y == null) continue;
      const dx = tgt.x - s.x;
      const dy = tgt.y - s.y;
      const lenSq = dx * dx + dy * dy;
      if (lenSq === 0) continue;
      const param = Math.max(
        0,
        Math.min(1, ((sx - s.x) * dx + (sy - s.y) * dy) / lenSq),
      );
      const projX = s.x + param * dx;
      const projY = s.y + param * dy;
      const dist = Math.sqrt((sx - projX) ** 2 + (sy - projY) ** 2);
      if (dist < 6) return link;
    }
    return null;
  }

  // ────────────────────────────────────────────────
  // Event handlers
  // ────────────────────────────────────────────────

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
      onHoveredNodeChange(node);
      onHoveredEdgeChange(null);
      onTooltipPosChange({ x: e.clientX, y: e.clientY });
    } else {
      const edge = findEdgeAt(sx, sy);
      onHoveredNodeChange(null);
      onHoveredEdgeChange(edge);
      if (edge) onTooltipPosChange({ x: e.clientX, y: e.clientY });
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
    onNodeClick(node);
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

  // ────────────────────────────────────────────────
  // Touch handlers
  // ────────────────────────────────────────────────

  function touchDist(a: React.Touch, b: React.Touch) {
    return Math.sqrt((a.clientX - b.clientX) ** 2 + (a.clientY - b.clientY) ** 2);
  }

  function handleTouchStart(e: React.TouchEvent<HTMLCanvasElement>) {
    e.preventDefault();
    const touches = e.touches;

    if (touches.length === 2) {
      pinchDistRef.current = touchDist(touches[0], touches[1]);
      return;
    }

    if (touches.length === 1) {
      const touch = touches[0];
      const { x: sx, y: sy } = canvasToSim(touch.clientX, touch.clientY);
      const node = findNodeAt(sx, sy);

      isDraggingRef.current = true;
      dragStartRef.current = { x: touch.clientX, y: touch.clientY };
      touchStartRef.current = { x: touch.clientX, y: touch.clientY };

      if (node) {
        dragNodeRef.current = node;
        node.fx = node.x;
        node.fy = node.y;
        simRef.current?.alphaTarget(0.3).restart();
      }
    }
  }

  function handleTouchMove(e: React.TouchEvent<HTMLCanvasElement>) {
    e.preventDefault();
    const touches = e.touches;

    if (touches.length === 2) {
      const dist = touchDist(touches[0], touches[1]);
      if (pinchDistRef.current > 0) {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const mx = (touches[0].clientX + touches[1].clientX) / 2 - rect.left;
        const my = (touches[0].clientY + touches[1].clientY) / 2 - rect.top;

        const t = transformRef.current;
        const zoomFactor = dist / pinchDistRef.current;
        const newScale = Math.max(0.1, Math.min(5, t.scale * zoomFactor));
        const ratio = newScale / t.scale;

        t.x = mx - ratio * (mx - t.x);
        t.y = my - ratio * (my - t.y);
        t.scale = newScale;

        rafRef.current = requestAnimationFrame(draw);
      }
      pinchDistRef.current = dist;
      return;
    }

    if (touches.length === 1) {
      const touch = touches[0];

      if (isDraggingRef.current && dragNodeRef.current) {
        const { x: sx, y: sy } = canvasToSim(touch.clientX, touch.clientY);
        dragNodeRef.current.fx = sx;
        dragNodeRef.current.fy = sy;
        simRef.current?.alpha(0.3).restart();
        return;
      }

      if (isDraggingRef.current) {
        const t = transformRef.current;
        t.x += touch.clientX - dragStartRef.current.x;
        t.y += touch.clientY - dragStartRef.current.y;
        dragStartRef.current = { x: touch.clientX, y: touch.clientY };
        rafRef.current = requestAnimationFrame(draw);
      }
    }
  }

  function handleTouchEnd(e: React.TouchEvent<HTMLCanvasElement>) {
    e.preventDefault();
    pinchDistRef.current = 0;

    if (e.touches.length === 0) {
      const ct = e.changedTouches[0];
      if (ct) {
        const dx = ct.clientX - touchStartRef.current.x;
        const dy = ct.clientY - touchStartRef.current.y;
        if (dx * dx + dy * dy < 100) {
          const { x: sx, y: sy } = canvasToSim(ct.clientX, ct.clientY);
          const node = findNodeAt(sx, sy);
          onNodeClick(node);
        }
      }

      isDraggingRef.current = false;
      if (dragNodeRef.current) {
        dragNodeRef.current.fx = null;
        dragNodeRef.current.fy = null;
        dragNodeRef.current = null;
        simRef.current?.alphaTarget(0);
      }
    }
  }

  // ────────────────────────────────────────────────
  // Render
  // ────────────────────────────────────────────────

  return (
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
            onHoveredNodeChange(null);
            onHoveredEdgeChange(null);
          }}
          onClick={handleClick}
          onWheel={handleWheel}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          className="w-full cursor-grab active:cursor-grabbing"
          style={{ height: CANVAS_HEIGHT, touchAction: "none" }}
        />

        {/* Node tooltip — Neo4j */}
        {hoveredNode && hoveredNode.meta.kind === "neo4j" && (
          <div
            className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
            style={{
              left: tooltipPos.x + 12,
              top: tooltipPos.y - 8,
            }}
          >
            <p className="font-medium">{hoveredNode.label}</p>
            <p className="text-xs text-muted-foreground">
              {hoveredNode.meta.entity_type} &middot;{" "}
              {hoveredNode.meta.stmt_count} statements &middot;{" "}
              {connectionCount(hoveredNode.nodeId)} connections
            </p>
          </div>
        )}

        {/* Node tooltip — Postgres */}
        {hoveredNode && hoveredNode.meta.kind === "postgres" && (
          <div
            className="pointer-events-none fixed z-50 max-w-xs rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
            style={{
              left: tooltipPos.x + 12,
              top: tooltipPos.y - 8,
            }}
          >
            <p className="font-medium">{hoveredNode.label}</p>
            <p className="text-xs text-muted-foreground">
              #{hoveredNode.meta.memoryId} &middot;{" "}
              {hoveredNode.meta.memory_type} &middot; importance{" "}
              {hoveredNode.meta.importance.toFixed(1)} &middot;{" "}
              {connectionCount(hoveredNode.nodeId)} connections
            </p>
            {hoveredNode.meta.cluster_label && (
              <p className="text-xs text-muted-foreground">
                Cluster: {hoveredNode.meta.cluster_label}
              </p>
            )}
            {hoveredNode.meta.project && (
              <ProjectPill name={hoveredNode.meta.project} />
            )}
          </div>
        )}

        {/* Edge tooltip — Neo4j */}
        {!hoveredNode && hoveredEdge && hoveredEdge.edgeMeta.kind === "neo4j" && (
          <div
            className="pointer-events-none fixed z-50 max-w-sm rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
            style={{
              left: tooltipPos.x + 12,
              top: tooltipPos.y - 8,
            }}
          >
            <p className="font-medium">{hoveredEdge.edgeLabel}</p>
            <p className="text-xs text-muted-foreground">
              {hoveredEdge.edgeMeta.fact}
            </p>
            <p className="text-xs text-muted-foreground/60">
              {hoveredEdge.edgeMeta.aspect}
            </p>
          </div>
        )}

        {/* Edge tooltip — Postgres */}
        {!hoveredNode && hoveredEdge && hoveredEdge.edgeMeta.kind === "postgres" && (
          <div
            className="pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-md"
            style={{
              left: tooltipPos.x + 12,
              top: tooltipPos.y - 8,
            }}
          >
            <p className="text-xs">
              <span className="font-medium">
                {hoveredEdge.edgeMeta.relation.replace("_", " ")}
              </span>{" "}
              {(hoveredEdge.source as SimNode).label} →{" "}
              {(hoveredEdge.target as SimNode).label}
            </p>
          </div>
        )}
      </div>

      {/* Legend — mode-aware */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {mode === "neo4j" ? (
          <>
            {Object.entries(ENTITY_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-muted-foreground">{type}</span>
              </div>
            ))}
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}
