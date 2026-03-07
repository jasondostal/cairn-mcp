import type { SimulationNodeDatum, SimulationLinkDatum } from "d3-force";
import { MEMORY_TYPE_OKLCH, MEMORY_TYPE_FALLBACK_OKLCH, relationColor } from "@/lib/colors";

// ────────────────────────────────────────────────────
// Mode type
// ────────────────────────────────────────────────────

export type GraphMode = "neo4j" | "postgres";

// ────────────────────────────────────────────────────
// Neo4j entity type colors
// ────────────────────────────────────────────────────

export const ENTITY_COLORS: Record<string, string> = {
  Person:       "oklch(0.70 0.18 70)",
  Organization: "oklch(0.60 0.22 16)",
  Place:        "oklch(0.65 0.17 162)",
  Event:        "oklch(0.65 0.22 340)",
  Project:      "oklch(0.55 0.20 264)",
  Task:         "oklch(0.65 0.18 45)",
  Technology:   "oklch(0.55 0.22 290)",
  Product:      "oklch(0.60 0.15 200)",
  Concept:      "oklch(0.50 0.04 264)",
};

export const ASPECT_COLORS: Record<string, string> = {
  Identity:     "oklch(0.70 0.18 70)",
  Knowledge:    "oklch(0.55 0.20 264)",
  Belief:       "oklch(0.55 0.22 290)",
  Preference:   "oklch(0.65 0.22 340)",
  Action:       "oklch(0.65 0.17 162)",
  Goal:         "oklch(0.60 0.15 175)",
  Directive:    "oklch(0.60 0.22 16)",
  Decision:     "oklch(0.65 0.18 45)",
  Event:        "oklch(0.60 0.15 200)",
  Problem:      "oklch(0.55 0.24 16)",
  Relationship: "oklch(0.50 0.20 264)",
};

export const ENTITY_TYPES = [
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
// Colors — sourced from lib/colors registry
// ────────────────────────────────────────────────────

export const TYPE_COLORS = MEMORY_TYPE_OKLCH;
export const RELATION_COLORS: Record<string, string> = {
  extends: relationColor("extends"),
  contradicts: relationColor("contradicts"),
  implements: relationColor("implements"),
  depends_on: relationColor("depends_on"),
  related: relationColor("related"),
};

export const CLUSTER_PALETTE = [
  "oklch(0.55 0.20 264)", "oklch(0.60 0.22 16)",  "oklch(0.65 0.17 162)",
  "oklch(0.70 0.18 70)",  "oklch(0.55 0.22 290)", "oklch(0.60 0.15 200)",
  "oklch(0.65 0.22 340)", "oklch(0.60 0.15 175)", "oklch(0.65 0.18 45)",
  "oklch(0.50 0.20 264)", "oklch(0.65 0.19 120)", "oklch(0.55 0.24 16)",
  "oklch(0.60 0.18 220)", "oklch(0.60 0.24 304)", "oklch(0.72 0.18 85)",
];
export const CLUSTER_UNASSIGNED_COLOR = "oklch(0.40 0.02 264)";

export const RELATION_TYPES = [
  "all", "extends", "contradicts", "implements", "depends_on", "related",
] as const;

// ────────────────────────────────────────────────────
// Shared defaults
// ────────────────────────────────────────────────────

export const DEFAULT_NODE_COLOR = MEMORY_TYPE_FALLBACK_OKLCH;
export const DEFAULT_EDGE_COLOR = "oklch(0.45 0.02 264)";
export const CANVAS_HEIGHT = 600;

// ────────────────────────────────────────────────────
// Unified simulation types
// ────────────────────────────────────────────────────

export interface SimNodeBase extends SimulationNodeDatum {
  nodeId: string;
  label: string;
  radius: number;
}

export interface Neo4jMeta {
  kind: "neo4j";
  entity_type: string;
  project_id: number;
  stmt_count: number;
}

export interface PgMeta {
  kind: "postgres";
  memoryId: number;
  memory_type: string;
  importance: number;
  project: string;
  cluster_id: number | null;
  cluster_label: string | null;
  age_days: number;
}

export type SimNode = SimNodeBase & { meta: Neo4jMeta | PgMeta };

export interface SimLinkBase extends SimulationLinkDatum<SimNode> {
  edgeLabel: string;
}

export interface Neo4jEdgeMeta {
  kind: "neo4j";
  fact: string;
  aspect: string;
}

export interface PgEdgeMeta {
  kind: "postgres";
  relation: string;
}

export type SimLink = SimLinkBase & { edgeMeta: Neo4jEdgeMeta | PgEdgeMeta };
