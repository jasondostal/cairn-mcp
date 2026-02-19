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
import {
  api,
  type GraphResult,
  type KnowledgeGraphResult,
} from "@/lib/api";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters } from "@/components/page-filters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { PageLayout } from "@/components/page-layout";

// ────────────────────────────────────────────────────
// Mode type
// ────────────────────────────────────────────────────

type GraphMode = "neo4j" | "postgres";

// ────────────────────────────────────────────────────
// Neo4j entity type colors
// ────────────────────────────────────────────────────

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

// ────────────────────────────────────────────────────
// Postgres memory type colors
// ────────────────────────────────────────────────────

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

const RELATION_COLORS: Record<string, string> = {
  extends: "#3b82f6",
  contradicts: "#ef4444",
  implements: "#22c55e",
  depends_on: "#f59e0b",
  related: "#6b7280",
};

const CLUSTER_PALETTE = [
  "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#6366f1",
  "#84cc16", "#e11d48", "#0ea5e9", "#d946ef", "#facc15",
];
const CLUSTER_UNASSIGNED_COLOR = "#4b5563";

const RELATION_TYPES = [
  "all", "extends", "contradicts", "implements", "depends_on", "related",
] as const;

// ────────────────────────────────────────────────────
// Shared defaults
// ────────────────────────────────────────────────────

const DEFAULT_NODE_COLOR = "#6b7280";
const DEFAULT_EDGE_COLOR = "#475569";
const CANVAS_HEIGHT = 600;

// ────────────────────────────────────────────────────
// Unified simulation types
// ────────────────────────────────────────────────────

interface SimNodeBase extends SimulationNodeDatum {
  nodeId: string; // stringified id for d3 (uuid for neo4j, "m-{id}" for pg)
  label: string;
  radius: number;
}

interface Neo4jMeta {
  kind: "neo4j";
  entity_type: string;
  project_id: number;
  stmt_count: number;
}

interface PgMeta {
  kind: "postgres";
  memoryId: number;
  memory_type: string;
  importance: number;
  project: string;
  cluster_id: number | null;
  cluster_label: string | null;
  age_days: number;
}

type SimNode = SimNodeBase & { meta: Neo4jMeta | PgMeta };

interface SimLinkBase extends SimulationLinkDatum<SimNode> {
  edgeLabel: string;
}

interface Neo4jEdgeMeta {
  kind: "neo4j";
  fact: string;
  aspect: string;
}

interface PgEdgeMeta {
  kind: "postgres";
  relation: string;
}

type SimLink = SimLinkBase & { edgeMeta: Neo4jEdgeMeta | PgEdgeMeta };

// ────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────

export default function GraphPage() {
  // --- Mode state ---
  const [mode, setMode] = useState<GraphMode>("postgres"); // default until probed
  const [neo4jAvailable, setNeo4jAvailable] = useState<boolean | null>(null); // null = probing
  const [probing, setProbing] = useState(true);

  // --- Data ---
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [pgRelationTypes, setPgRelationTypes] = useState<Record<string, number>>({});
  const [neo4jEntityTypes, setNeo4jEntityTypes] = useState<Record<string, number>>({});

  // --- Filters ---
  const filters = usePageFilters();
  // Neo4j filters
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  // Postgres filters
  const [relationType, setRelationType] = useState("all");
  const [colorMode, setColorMode] = useState<"type" | "cluster">("type");

  // --- Simulation ---
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const simRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);

  // --- Interaction ---
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<SimLink | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  // --- Zoom/pan ---
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const dragNodeRef = useRef<SimNode | null>(null);

  // --- Touch ---
  const pinchDistRef = useRef(0);
  const touchStartRef = useRef({ x: 0, y: 0 });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);

  // ────────────────────────────────────────────────
  // Mode detection on mount
  // ────────────────────────────────────────────────

  useEffect(() => {
    const saved = localStorage.getItem("cairn-graph-mode") as GraphMode | null;

    // Probe Neo4j availability via status endpoint
    api
      .status()
      .then((status) => {
        const hasNeo4j = status.graph_backend === "neo4j";
        setNeo4jAvailable(hasNeo4j);
        if (hasNeo4j) {
          setMode(saved === "postgres" ? "postgres" : "neo4j");
        } else {
          setMode("postgres");
        }
      })
      .catch(() => {
        setNeo4jAvailable(false);
        setMode("postgres");
      })
      .finally(() => setProbing(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load data after probing completes
  useEffect(() => {
    if (!probing) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probing]);

  // ────────────────────────────────────────────────
  // Mode switch
  // ────────────────────────────────────────────────

  function switchMode(newMode: GraphMode) {
    setMode(newMode);
    localStorage.setItem("cairn-graph-mode", newMode);
    setSelectedNode(null);
    setHoveredNode(null);
    setHoveredEdge(null);
    // Load will be triggered by the effect below
  }

  // Auto-reload on mode or filter changes (after initial probe)
  const modeRef = useRef(mode);
  const prevProjectRef = useRef(filters.projectFilter);
  const prevEntityRef = useRef(entityTypeFilter);
  const prevRelRef = useRef(relationType);
  useEffect(() => {
    if (probing) return;
    const modeChanged = modeRef.current !== mode;
    const projectChanged = prevProjectRef.current !== filters.projectFilter;
    const entityChanged = prevEntityRef.current !== entityTypeFilter;
    const relChanged = prevRelRef.current !== relationType;

    modeRef.current = mode;
    prevProjectRef.current = filters.projectFilter;
    prevEntityRef.current = entityTypeFilter;
    prevRelRef.current = relationType;

    if (modeChanged || projectChanged || entityChanged || relChanged) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, probing, filters.projectFilter, entityTypeFilter, relationType]);

  // ────────────────────────────────────────────────
  // Data loading
  // ────────────────────────────────────────────────

  function load() {
    if (mode === "neo4j") {
      loadNeo4j();
    } else {
      loadPostgres();
    }
  }

  function loadNeo4j() {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    const projectParam = filters.showAllProjects ? undefined : filters.projectFilter.join(",");
    api
      .knowledgeGraph({
        project: projectParam,
        entity_type: entityTypeFilter === "all" ? undefined : entityTypeFilter,
      })
      .then((result) => {
        setNodeCount(result.stats.node_count);
        setEdgeCount(result.stats.edge_count);
        setNeo4jEntityTypes(result.stats.entity_types || {});
        initNeo4jSimulation(result);
      })
      .catch((err) => {
        const msg = err?.message || "Failed to load knowledge graph";
        // Mid-session fallback: if Neo4j fails, auto-switch to Postgres
        if (neo4jAvailable) {
          setNeo4jAvailable(false);
          setMode("postgres");
          localStorage.setItem("cairn-graph-mode", "postgres");
          return; // load() will be triggered by mode change effect
        }
        setError(msg);
      })
      .finally(() => setLoading(false));
  }

  function loadPostgres() {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    const projectParam = filters.showAllProjects ? undefined : filters.projectFilter.join(",");
    api
      .graph({
        project: projectParam,
        relation_type: relationType === "all" ? undefined : relationType,
      })
      .then((result) => {
        setNodeCount(result.stats.node_count);
        setEdgeCount(result.stats.edge_count);
        setPgRelationTypes(result.stats.relation_types || {});
        initPostgresSimulation(result);
      })
      .catch((err) => setError(err?.message || "Failed to load graph"))
      .finally(() => setLoading(false));
  }

  // ────────────────────────────────────────────────
  // Simulation init — Neo4j
  // ────────────────────────────────────────────────

  function initNeo4jSimulation(result: KnowledgeGraphResult) {
    if (simRef.current) simRef.current.stop();
    cancelAnimationFrame(rafRef.current);

    const width = containerRef.current?.clientWidth || 800;
    const nodeMap = new Map<string, SimNode>();

    const nodes: SimNode[] = result.nodes.map((n) => {
      const radius = Math.max(5, Math.min(20, 4 + Math.sqrt(n.stmt_count) * 3));
      const node: SimNode = {
        nodeId: n.uuid,
        label: n.name,
        radius,
        meta: {
          kind: "neo4j",
          entity_type: n.entity_type,
          project_id: n.project_id,
          stmt_count: n.stmt_count,
        },
        x: width / 2 + (Math.random() - 0.5) * 300,
        y: CANVAS_HEIGHT / 2 + (Math.random() - 0.5) * 300,
      };
      nodeMap.set(n.uuid, node);
      return node;
    });

    const links: SimLink[] = result.edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
        edgeLabel: e.predicate,
        edgeMeta: { kind: "neo4j" as const, fact: e.fact, aspect: e.aspect },
      }));

    startSimulation(nodes, links, width, { linkDistance: 120, chargeStrength: -200 });
  }

  // ────────────────────────────────────────────────
  // Simulation init — Postgres
  // ────────────────────────────────────────────────

  function initPostgresSimulation(result: GraphResult) {
    if (simRef.current) simRef.current.stop();
    cancelAnimationFrame(rafRef.current);

    const width = containerRef.current?.clientWidth || 800;
    const nodeMap = new Map<string, SimNode>();

    const nodes: SimNode[] = result.nodes.map((n) => {
      const id = `m-${n.id}`;
      const node: SimNode = {
        nodeId: id,
        label: n.summary || `#${n.id}`,
        radius: n.size ?? (5 + n.importance * 8),
        meta: {
          kind: "postgres",
          memoryId: n.id,
          memory_type: n.memory_type,
          importance: n.importance,
          project: n.project,
          cluster_id: n.cluster_id,
          cluster_label: n.cluster_label,
          age_days: n.age_days ?? 0,
        },
        x: width / 2 + (Math.random() - 0.5) * 200,
        y: CANVAS_HEIGHT / 2 + (Math.random() - 0.5) * 200,
      };
      nodeMap.set(id, node);
      return node;
    });

    const links: SimLink[] = result.edges
      .filter((e) => nodeMap.has(`m-${e.source}`) && nodeMap.has(`m-${e.target}`))
      .map((e) => ({
        source: nodeMap.get(`m-${e.source}`)!,
        target: nodeMap.get(`m-${e.target}`)!,
        edgeLabel: e.relation,
        edgeMeta: { kind: "postgres" as const, relation: e.relation },
      }));

    startSimulation(nodes, links, width, { linkDistance: 100, chargeStrength: -150 });
  }

  // ────────────────────────────────────────────────
  // Shared simulation start
  // ────────────────────────────────────────────────

  function startSimulation(
    nodes: SimNode[],
    links: SimLink[],
    width: number,
    params: { linkDistance: number; chargeStrength: number },
  ) {
    nodesRef.current = nodes;
    linksRef.current = links;
    transformRef.current = { x: 0, y: 0, scale: 1 };

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.nodeId)
          .distance(params.linkDistance),
      )
      .force("charge", forceManyBody<SimNode>().strength(params.chargeStrength))
      .force("center", forceCenter(width / 2, CANVAS_HEIGHT / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d) => d.radius + 4),
      )
      .alphaDecay(0.01)
      .on("tick", () => {
        rafRef.current = requestAnimationFrame(draw);
      });

    simRef.current = sim;
  }

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
  }, [hoveredNode, selectedNode, searchTerm, mode, colorMode]);

  // ────────────────────────────────────────────────
  // Effects
  // ────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (simRef.current) simRef.current.stop();
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

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

    if (!node) {
      setSelectedNode(null);
      return;
    }

    // Mode-aware click: Neo4j → side panel, Postgres → memory sheet
    if (node.meta.kind === "postgres") {
      openSheet(node.meta.memoryId);
    } else {
      setSelectedNode(node === selectedNode ? null : node);
    }
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
      // Pinch start
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
      // Pinch zoom
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
      // Check for tap (vs drag)
      const ct = e.changedTouches[0];
      if (ct) {
        const dx = ct.clientX - touchStartRef.current.x;
        const dy = ct.clientY - touchStartRef.current.y;
        if (dx * dx + dy * dy < 100) {
          // Tap — trigger click behavior
          const { x: sx, y: sy } = canvasToSim(ct.clientX, ct.clientY);
          const node = findNodeAt(sx, sy);
          if (node) {
            if (node.meta.kind === "postgres") {
              openSheet(node.meta.memoryId);
            } else {
              setSelectedNode(node === selectedNode ? null : node);
            }
          } else {
            setSelectedNode(null);
          }
        }
      }

      // Release dragged node
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
  // Helpers
  // ────────────────────────────────────────────────

  function connectionCount(nodeId: string): number {
    return linksRef.current.filter((l) => {
      const s = l.source as SimNode;
      const tgt = l.target as SimNode;
      return s.nodeId === nodeId || tgt.nodeId === nodeId;
    }).length;
  }

  // Connections for selected node (Neo4j inline panel)
  const selectedConnections =
    selectedNode && selectedNode.meta.kind === "neo4j"
      ? linksRef.current
          .filter((l) => {
            const s = l.source as SimNode;
            const tgt = l.target as SimNode;
            return s.nodeId === selectedNode.nodeId || tgt.nodeId === selectedNode.nodeId;
          })
          .map((l) => {
            const s = l.source as SimNode;
            const tgt = l.target as SimNode;
            const other = s.nodeId === selectedNode.nodeId ? tgt : s;
            const direction = s.nodeId === selectedNode.nodeId ? "out" : "in";
            const em = l.edgeMeta.kind === "neo4j" ? l.edgeMeta : null;
            return {
              other,
              predicate: l.edgeLabel,
              fact: em?.fact ?? "",
              aspect: em?.aspect ?? "",
              direction,
            };
          })
      : [];

  // Empty state check
  const hasData = nodeCount > 0;

  // ────────────────────────────────────────────────
  // Render
  // ────────────────────────────────────────────────

  return (
    <PageLayout
      title="Knowledge Graph"
      titleExtra={
        <div className="flex items-center gap-2">
          {hasData && (
            <Badge variant="secondary" className="font-mono text-xs">
              {nodeCount} {mode === "neo4j" ? "entities" : "nodes"},{" "}
              {edgeCount} {mode === "neo4j" ? "relationships" : "edges"}
            </Badge>
          )}

          {/* Toggle pill — only when both backends available */}
          {neo4jAvailable && (
            <div className="inline-flex rounded-md border border-border bg-muted p-0.5">
              <button
                onClick={() => switchMode("neo4j")}
                className={`rounded-sm px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  mode === "neo4j"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Entities
              </button>
              <button
                onClick={() => switchMode("postgres")}
                className={`rounded-sm px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  mode === "postgres"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Memories
              </button>
            </div>
          )}
        </div>
      }
      filters={
        <PageFilters
          filters={filters}
          extra={
            <>
              {/* Neo4j: entity search (client-side highlight, no reload) */}
              {mode === "neo4j" && (
                <Input
                  placeholder="Search entities..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-48"
                />
              )}

              {/* Neo4j: entity type buttons */}
              {mode === "neo4j" && (
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
              )}

              {/* Postgres: relation type buttons */}
              {mode === "postgres" && (
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
              )}

              {/* Postgres: color mode toggle */}
              {mode === "postgres" && (
                <Button
                  variant={colorMode === "cluster" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setColorMode(colorMode === "cluster" ? "type" : "cluster")}
                >
                  {colorMode === "cluster" ? "Color: Cluster" : "Color: Type"}
                </Button>
              )}
            </>
          }
        />
      }
    >
      {(loading || probing) && <Skeleton className="h-[600px]" />}

      {error && <ErrorState message="Failed to load graph" detail={error} />}

      {!loading && !probing && !error && !hasData && (
        <div className="flex h-[400px] items-center justify-center rounded-lg border border-border bg-card">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              {mode === "neo4j"
                ? "No entities found in the knowledge graph."
                : "No relationships found."}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {mode === "neo4j"
                ? "Knowledge extraction runs automatically when memories are stored (requires Neo4j + knowledge_extraction enabled)."
                : "Relationships are extracted automatically when memories are stored. Try selecting a different project or clearing filters."}
            </p>
          </div>
        </div>
      )}

      {!loading && !probing && !error && hasData && (
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
                    <p className="text-xs text-muted-foreground">
                      {hoveredNode.meta.project}
                    </p>
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

          {/* Side panel — Neo4j entity details */}
          {selectedNode && selectedNode.meta.kind === "neo4j" && (
            <div className="w-72 shrink-0 space-y-3 rounded-lg border border-border bg-card p-4">
              <div>
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{
                      backgroundColor:
                        ENTITY_COLORS[selectedNode.meta.entity_type] ||
                        DEFAULT_NODE_COLOR,
                    }}
                  />
                  <h3 className="font-semibold text-sm">{selectedNode.label}</h3>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {selectedNode.meta.entity_type} &middot;{" "}
                  {selectedNode.meta.stmt_count} statements &middot;{" "}
                  {connectionCount(selectedNode.nodeId)} connections
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
                                conn.other.meta.kind === "neo4j"
                                  ? ENTITY_COLORS[conn.other.meta.entity_type] ||
                                    DEFAULT_NODE_COLOR
                                  : DEFAULT_NODE_COLOR,
                            }}
                          />
                          <span>{conn.other.label}</span>
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

      {/* Memory sheet for Postgres mode click-through */}
      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
