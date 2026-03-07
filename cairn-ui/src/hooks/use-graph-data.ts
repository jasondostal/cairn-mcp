"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
} from "d3-force";
import {
  api,
  type GraphResult,
  type KnowledgeGraphResult,
} from "@/lib/api";
import type { usePageFilters } from "@/lib/use-page-filters";
import {
  type GraphMode,
  type SimNode,
  type SimLink,
  CANVAS_HEIGHT,
} from "@/components/graph/graph-types";

// ────────────────────────────────────────────────────
// Hook
// ────────────────────────────────────────────────────

export function useGraphData(
  filters: ReturnType<typeof usePageFilters>,
  entityTypeFilter: string,
  relationType: string,
  containerRef: React.RefObject<HTMLDivElement | null>,
  drawRequestRef: React.MutableRefObject<(() => void) | null>,
) {
  // --- Mode state ---
  const [mode, setMode] = useState<GraphMode>("postgres");
  const [neo4jAvailable, setNeo4jAvailable] = useState<boolean | null>(null);
  const [probing, setProbing] = useState(true);

  // --- Data ---
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [, setPgRelationTypes] = useState<Record<string, number>>({});
  const [, setNeo4jEntityTypes] = useState<Record<string, number>>({});

  // --- Simulation ---
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const simRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });

  // ────────────────────────────────────────────────
  // Mode detection on mount
  // ────────────────────────────────────────────────

  useEffect(() => {
    const saved = localStorage.getItem("cairn-graph-mode") as GraphMode | null;

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
  }, []);

  // Load data after probing completes
  useEffect(() => {
    if (!probing) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probing]);

  // ────────────────────────────────────────────────
  // Mode switch
  // ────────────────────────────────────────────────

  const switchMode = useCallback((newMode: GraphMode) => {
    setMode(newMode);
    localStorage.setItem("cairn-graph-mode", newMode);
  }, []);

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
        if (neo4jAvailable) {
          setNeo4jAvailable(false);
          setMode("postgres");
          localStorage.setItem("cairn-graph-mode", "postgres");
          return;
        }
        setError(msg);
      })
      .finally(() => setLoading(false));
  }

  function loadPostgres() {
    setLoading(true);
    setError(null);
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
        drawRequestRef.current?.();
      });

    simRef.current = sim;
  }

  // Cleanup
  useEffect(() => {
    return () => {
      if (simRef.current) simRef.current.stop();
    };
  }, []);

  // ────────────────────────────────────────────────
  // Connection count helper
  // ────────────────────────────────────────────────

  const connectionCount = useCallback((nodeId: string): number => {
    return linksRef.current.filter((l) => {
      const s = l.source as SimNode;
      const tgt = l.target as SimNode;
      return s.nodeId === nodeId || tgt.nodeId === nodeId;
    }).length;
  }, []);

  return {
    mode,
    neo4jAvailable,
    probing,
    loading,
    error,
    nodeCount,
    edgeCount,
    nodesRef,
    linksRef,
    simRef,
    transformRef,
    switchMode,
    reload: load,
    connectionCount,
  };
}
