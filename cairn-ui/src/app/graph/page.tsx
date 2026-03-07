"use client";

import { useRef, useState } from "react";
import { usePageFilters } from "@/lib/use-page-filters";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useGraphData } from "@/hooks/use-graph-data";
import { PageFilters } from "@/components/page-filters";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { PageLayout } from "@/components/page-layout";
import { GraphCanvas } from "@/components/graph/graph-canvas";
import { GraphFilters } from "@/components/graph/graph-filters";
import { NodeDetailPanel } from "@/components/graph/node-detail-panel";
import type { SimNode, SimLink } from "@/components/graph/graph-types";

// ────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────

export default function GraphPage() {
  // --- Filters ---
  const filters = usePageFilters();
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [relationType, setRelationType] = useState("all");
  const [colorMode, setColorMode] = useState<"type" | "cluster">("type");

  // --- Refs shared between hook and canvas ---
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawRequestRef = useRef<(() => void) | null>(null);

  // --- Data & simulation ---
  const {
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
    reload,
    connectionCount,
  } = useGraphData(filters, entityTypeFilter, relationType, containerRef, drawRequestRef);

  // --- Interaction ---
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<SimLink | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  // --- Mode switch ---
  function handleSwitchMode(newMode: "neo4j" | "postgres") {
    switchMode(newMode);
    setSelectedNode(null);
    setHoveredNode(null);
    setHoveredEdge(null);
  }

  // --- Node click (mode-aware) ---
  function handleNodeClick(node: SimNode | null) {
    if (!node) {
      setSelectedNode(null);
      return;
    }
    if (node.meta.kind === "postgres") {
      openSheet(node.meta.memoryId);
    } else {
      setSelectedNode(node === selectedNode ? null : node);
    }
  }

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
                onClick={() => handleSwitchMode("neo4j")}
                className={`rounded-sm px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  mode === "neo4j"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Entities
              </button>
              <button
                onClick={() => handleSwitchMode("postgres")}
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
            <GraphFilters
              mode={mode}
              searchTerm={searchTerm}
              onSearchTermChange={setSearchTerm}
              entityTypeFilter={entityTypeFilter}
              onEntityTypeFilterChange={setEntityTypeFilter}
              relationType={relationType}
              onRelationTypeChange={setRelationType}
              colorMode={colorMode}
              onColorModeChange={setColorMode}
              projects={filters.projects}
              defaultProject={filters.projectFilter[0]}
              onEntityCreated={reload}
            />
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
          <GraphCanvas
            mode={mode}
            colorMode={colorMode}
            searchTerm={searchTerm}
            nodesRef={nodesRef}
            linksRef={linksRef}
            simRef={simRef}
            transformRef={transformRef}
            containerRef={containerRef}
            canvasRef={canvasRef}
            drawRequestRef={drawRequestRef}
            hoveredNode={hoveredNode}
            hoveredEdge={hoveredEdge}
            selectedNode={selectedNode}
            tooltipPos={tooltipPos}
            onHoveredNodeChange={setHoveredNode}
            onHoveredEdgeChange={setHoveredEdge}
            onTooltipPosChange={setTooltipPos}
            onNodeClick={handleNodeClick}
            connectionCount={connectionCount}
          />

          {/* Side panel — Neo4j entity details */}
          {selectedNode && selectedNode.meta.kind === "neo4j" && (
            <NodeDetailPanel
              selectedNode={selectedNode}
              linksRef={linksRef}
              connectionCount={connectionCount}
              onSelectNode={setSelectedNode}
              onReload={reload}
            />
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
