"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { X } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
  // Ephemeral types
  "hypothesis", "question", "tension", "connection", "thread", "intuition",
] as const;

export const MEMORIES_TIME_PRESETS = [
  { label: "7d",  value: 7,   color: "oklch(0.72 0.17 135)" },  // mint
  { label: "14d", value: 14,  color: "oklch(0.70 0.17 220)" },  // sky
  { label: "30d", value: 30,  color: "oklch(0.68 0.18 270)" },  // periwinkle
  { label: "90d", value: 90,  color: "oklch(0.66 0.19 320)" },  // orchid
  { label: "All", value: 9999, color: "oklch(0.70 0.17 350)" },  // blush
];

export const SORT_OPTIONS = [
  { label: "Recent",    value: "recent",    color: "oklch(0.72 0.18 240)" },  // blue
  { label: "Important", value: "important", color: "oklch(0.70 0.19 15)" },   // rose
  { label: "Relevance", value: "relevance", color: "oklch(0.68 0.19 300)" },  // violet
] as const;

export const VIEW_OPTIONS = [
  { label: "Chrono",  value: "chrono",  color: "oklch(0.72 0.18 145)" },  // emerald
  { label: "By type", value: "type",    color: "oklch(0.70 0.19 55)" },   // tangerine
] as const;

/* OKLCH lifecycle toggle colors */
export const LC = {
  all:          "oklch(0.72 0.19 165)",   // teal
  crystallized: "oklch(0.65 0.18 260)",   // indigo
  ephemeral:    "oklch(0.78 0.18 75)",    // amber
} as const;

export type Lifecycle = "all" | "crystallized" | "ephemeral";

export const LIFECYCLE_OPTIONS: { label: string; value: Lifecycle; color: string }[] = [
  { label: "All",          value: "all",          color: LC.all },
  { label: "Crystallized", value: "crystallized",  color: LC.crystallized },
  { label: "Ephemeral",    value: "ephemeral",     color: LC.ephemeral },
];

/* ------------------------------------------------------------------ */
/*  OKLCH Toggle (reusable)                                            */
/* ------------------------------------------------------------------ */

export function OklchToggle<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: readonly { label: string; value: T; color: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => { if (v) onChange(v as T); }}
    >
      {options.map((opt) => (
        <ToggleGroupItem
          key={opt.value}
          value={opt.value}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            value === opt.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${opt.color} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${opt.color} 40%, transparent)`,
                  color: opt.color,
                }
              : undefined
          }
        >
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/* ------------------------------------------------------------------ */
/*  Lifecycle Toggle                                                   */
/* ------------------------------------------------------------------ */

export function LifecycleToggle({
  value,
  onChange,
}: {
  value: Lifecycle;
  onChange: (v: Lifecycle) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => { if (v) onChange(v as Lifecycle); }}
    >
      {LIFECYCLE_OPTIONS.map((opt) => (
        <ToggleGroupItem
          key={opt.value}
          value={opt.value}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            value === opt.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${opt.color} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${opt.color} 40%, transparent)`,
                  color: opt.color,
                }
              : undefined
          }
        >
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/* ------------------------------------------------------------------ */
/*  Active Filter Pills                                                */
/* ------------------------------------------------------------------ */

export interface ActiveFilter {
  key: string;
  label: string;
  color?: string;
  onRemove: () => void;
}

export function ActiveFilterBar({ filters }: { filters: ActiveFilter[] }) {
  if (filters.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-2">
      <span className="text-[11px] text-muted-foreground/70">Active:</span>
      {filters.map((f) => (
        <button
          key={f.key}
          onClick={f.onRemove}
          className="group inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors hover:bg-destructive/10"
          style={f.color ? {
            backgroundColor: `color-mix(in oklch, ${f.color} 12%, transparent)`,
            borderColor: `color-mix(in oklch, ${f.color} 30%, transparent)`,
            border: "1px solid",
            color: f.color,
          } : {
            backgroundColor: "hsl(var(--muted))",
            color: "hsl(var(--muted-foreground))",
          }}
        >
          {f.label}
          <X className="h-2.5 w-2.5 opacity-50 group-hover:opacity-100" />
        </button>
      ))}
      {filters.length > 1 && (
        <button
          onClick={() => filters.forEach((f) => f.onRemove())}
          className="text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors ml-1"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
