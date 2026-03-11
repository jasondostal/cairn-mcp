import {
  Activity,
  BarChart3,
  Brain,
  Calendar,
  DollarSign,
  Cpu,
  HeartPulse,
  Kanban,
  Layers,
  PieChart,
  FolderOpen,
  TrendingUp,
} from "lucide-react";
import type { ComponentType } from "react";

// ---------------------------------------------------------------------------
// Types — own definitions matching RGL v2's LayoutItem / ResponsiveLayouts
// ---------------------------------------------------------------------------

export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
}

/** Layout for a single breakpoint (array of items) */
export type BreakpointLayout = readonly LayoutItem[];

/** Layouts keyed by breakpoint name */
export type DashboardLayouts = Partial<Record<string, BreakpointLayout>>;

export interface WidgetDefinition {
  id: string;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  /** Default layout per breakpoint */
  layouts: { lg: LayoutItem; md: LayoutItem; sm: LayoutItem };
}

// ---------------------------------------------------------------------------
// Grid configuration
// ---------------------------------------------------------------------------

export const GRID_COLS = { lg: 12, md: 6, sm: 1 } as const;
export const GRID_ROW_HEIGHT = 40;
export const GRID_MARGIN: [number, number] = [16, 16];
export const GRID_BREAKPOINTS = { lg: 1200, md: 768, sm: 0 } as const;

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export const WIDGET_REGISTRY: WidgetDefinition[] = [
  {
    id: "operational-strip",
    label: "Operational Status",
    description: "Work items, gated items, and active sessions",
    icon: Kanban,
    layouts: {
      lg: { i: "operational-strip", x: 0, y: 0, w: 12, h: 3, minW: 6, minH: 2 },
      md: { i: "operational-strip", x: 0, y: 0, w: 6, h: 3, minW: 3, minH: 2 },
      sm: { i: "operational-strip", x: 0, y: 0, w: 1, h: 3, minW: 1, minH: 2 },
    },
  },
  {
    id: "entity-growth",
    label: "Entity Growth",
    description: "Stacked area chart of memories, projects, clusters over time",
    icon: TrendingUp,
    layouts: {
      lg: { i: "entity-growth", x: 0, y: 3, w: 12, h: 9, minW: 6, minH: 4 },
      md: { i: "entity-growth", x: 0, y: 3, w: 6, h: 9, minW: 3, minH: 4 },
      sm: { i: "entity-growth", x: 0, y: 3, w: 1, h: 9, minW: 1, minH: 4 },
    },
  },
  {
    id: "memory-type-growth",
    label: "Memory Type Growth",
    description: "Stacked area chart of memory types over time",
    icon: Layers,
    layouts: {
      lg: { i: "memory-type-growth", x: 0, y: 12, w: 6, h: 9, minW: 4, minH: 4 },
      md: { i: "memory-type-growth", x: 0, y: 12, w: 6, h: 9, minW: 3, minH: 4 },
      sm: { i: "memory-type-growth", x: 0, y: 12, w: 1, h: 9, minW: 1, minH: 4 },
    },
  },
  {
    id: "token-usage",
    label: "Token Usage",
    description: "Tokens in vs tokens out over time",
    icon: Activity,
    layouts: {
      lg: { i: "token-usage", x: 6, y: 12, w: 6, h: 9, minW: 4, minH: 4 },
      md: { i: "token-usage", x: 0, y: 21, w: 6, h: 9, minW: 3, minH: 4 },
      sm: { i: "token-usage", x: 0, y: 21, w: 1, h: 9, minW: 1, minH: 4 },
    },
  },
  {
    id: "activity-heatmap",
    label: "Activity Heatmap",
    description: "GitHub-style contribution heatmap (365 days)",
    icon: Calendar,
    layouts: {
      lg: { i: "activity-heatmap", x: 0, y: 21, w: 12, h: 5, minW: 6, minH: 3 },
      md: { i: "activity-heatmap", x: 0, y: 30, w: 6, h: 5, minW: 3, minH: 3 },
      sm: { i: "activity-heatmap", x: 0, y: 30, w: 1, h: 5, minW: 1, minH: 3 },
    },
  },
  {
    id: "health-strip",
    label: "System Health",
    description: "Embedding model, LLM, and digest health status",
    icon: Cpu,
    layouts: {
      lg: { i: "health-strip", x: 0, y: 26, w: 12, h: 5, minW: 6, minH: 2 },
      md: { i: "health-strip", x: 0, y: 35, w: 6, h: 5, minW: 3, minH: 2 },
      sm: { i: "health-strip", x: 0, y: 35, w: 1, h: 5, minW: 1, minH: 2 },
    },
  },
  {
    id: "operations-volume",
    label: "Operations Volume",
    description: "Bar chart of operations and errors over time",
    icon: BarChart3,
    layouts: {
      lg: { i: "operations-volume", x: 0, y: 31, w: 6, h: 9, minW: 4, minH: 4 },
      md: { i: "operations-volume", x: 0, y: 40, w: 6, h: 9, minW: 3, minH: 4 },
      sm: { i: "operations-volume", x: 0, y: 40, w: 1, h: 9, minW: 1, minH: 4 },
    },
  },
  {
    id: "cost-projection",
    label: "Cost Projection",
    description: "Estimated costs by model with monthly/annual projections",
    icon: DollarSign,
    layouts: {
      lg: { i: "cost-projection", x: 6, y: 31, w: 6, h: 7, minW: 4, minH: 4 },
      md: { i: "cost-projection", x: 0, y: 49, w: 6, h: 7, minW: 3, minH: 4 },
      sm: { i: "cost-projection", x: 0, y: 49, w: 1, h: 7, minW: 1, minH: 4 },
    },
  },
  {
    id: "model-performance",
    label: "Model Performance",
    description: "Latency percentiles, error rates, and token counts by model",
    icon: Brain,
    layouts: {
      lg: { i: "model-performance", x: 0, y: 40, w: 6, h: 7, minW: 4, minH: 4 },
      md: { i: "model-performance", x: 0, y: 56, w: 6, h: 7, minW: 3, minH: 4 },
      sm: { i: "model-performance", x: 0, y: 56, w: 1, h: 7, minW: 1, minH: 4 },
    },
  },
  {
    id: "project-breakdown",
    label: "Project Breakdown",
    description: "Operations, tokens, and trends per project",
    icon: FolderOpen,
    layouts: {
      lg: { i: "project-breakdown", x: 6, y: 40, w: 6, h: 7, minW: 4, minH: 4 },
      md: { i: "project-breakdown", x: 0, y: 63, w: 6, h: 7, minW: 3, minH: 4 },
      sm: { i: "project-breakdown", x: 0, y: 63, w: 1, h: 7, minW: 1, minH: 4 },
    },
  },
  {
    id: "memory-type-bar",
    label: "Memory Type Distribution",
    description: "Proportional bar of memory types",
    icon: PieChart,
    layouts: {
      lg: { i: "memory-type-bar", x: 0, y: 47, w: 12, h: 3, minW: 6, minH: 2 },
      md: { i: "memory-type-bar", x: 0, y: 70, w: 6, h: 3, minW: 3, minH: 2 },
      sm: { i: "memory-type-bar", x: 0, y: 70, w: 1, h: 3, minW: 1, minH: 2 },
    },
  },
  {
    id: "live-pulse",
    label: "Live Pulse",
    description: "Real-time EKG — ops/sec, latency, tokens, errors streamed via SSE",
    icon: HeartPulse,
    layouts: {
      lg: { i: "live-pulse", x: 0, y: 50, w: 12, h: 8, minW: 4, minH: 5 },
      md: { i: "live-pulse", x: 0, y: 73, w: 6, h: 8, minW: 3, minH: 5 },
      sm: { i: "live-pulse", x: 0, y: 73, w: 1, h: 8, minW: 1, minH: 5 },
    },
  },
];

/** O(1) lookup by widget id */
export const WIDGET_MAP = new Map(WIDGET_REGISTRY.map((w) => [w.id, w]));

/** All widget IDs in default order */
export const DEFAULT_VISIBLE_WIDGETS = WIDGET_REGISTRY.map((w) => w.id);

/** Build default RGL Layouts from registry */
export function getDefaultLayouts(): DashboardLayouts {
  const lg: LayoutItem[] = [];
  const md: LayoutItem[] = [];
  const sm: LayoutItem[] = [];
  for (const widget of WIDGET_REGISTRY) {
    lg.push(widget.layouts.lg);
    md.push(widget.layouts.md);
    sm.push(widget.layouts.sm);
  }
  return { lg, md, sm };
}
