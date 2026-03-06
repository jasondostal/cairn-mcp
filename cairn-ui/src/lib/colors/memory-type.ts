/**
 * Memory type color registry.
 *
 * Single source of truth — consumed by MemoryTypeBadge, MemoryTypeBar,
 * graph visualization, and any future surface that renders memory types.
 *
 * Values reference CSS custom properties defined in globals.css so they
 * respect light/dark theming automatically when used via Tailwind classes.
 * The raw OKLCH values are exported for inline style contexts (canvas, SVG).
 */

/** CSS class mappings (use in className) */
export const MEMORY_TYPE_CLASSES: Record<string, { bg: string; text: string; border: string }> = {
  note:           { bg: "bg-type-note",           text: "text-type-note",           border: "border-type-note" },
  decision:       { bg: "bg-type-decision",       text: "text-type-decision",       border: "border-type-decision" },
  rule:           { bg: "bg-type-rule",           text: "text-type-rule",           border: "border-type-rule" },
  "code-snippet": { bg: "bg-type-code-snippet",   text: "text-type-code-snippet",   border: "border-type-code-snippet" },
  learning:       { bg: "bg-type-learning",       text: "text-type-learning",       border: "border-type-learning" },
  research:       { bg: "bg-type-research",       text: "text-type-research",       border: "border-type-research" },
  discussion:     { bg: "bg-type-discussion",     text: "text-type-discussion",     border: "border-type-discussion" },
  progress:       { bg: "bg-type-progress",       text: "text-type-progress",       border: "border-type-progress" },
  task:           { bg: "bg-type-task",           text: "text-type-task",           border: "border-type-task" },
  debug:          { bg: "bg-type-debug",          text: "text-type-debug",          border: "border-type-debug" },
  design:         { bg: "bg-type-design",         text: "text-type-design",         border: "border-type-design" },
};

/** Raw OKLCH values for canvas/SVG/inline style contexts */
export const MEMORY_TYPE_OKLCH: Record<string, string> = {
  note:           "oklch(0.55 0.20 264)",
  decision:       "oklch(0.70 0.18 70)",
  rule:           "oklch(0.60 0.22 16)",
  "code-snippet": "oklch(0.65 0.17 162)",
  learning:       "oklch(0.60 0.24 304)",
  research:       "oklch(0.60 0.15 200)",
  discussion:     "oklch(0.65 0.18 45)",
  progress:       "oklch(0.60 0.18 145)",
  task:           "oklch(0.55 0.20 290)",
  debug:          "oklch(0.65 0.20 30)",
  design:         "oklch(0.55 0.18 250)",
};

export const MEMORY_TYPE_FALLBACK_OKLCH = "oklch(0.45 0 0)";

/** All known memory types (ordered by typical frequency) */
export const MEMORY_TYPES = Object.keys(MEMORY_TYPE_OKLCH);

/** Get OKLCH color for a memory type, with fallback */
export function memoryTypeColor(type: string): string {
  return MEMORY_TYPE_OKLCH[type] ?? MEMORY_TYPE_FALLBACK_OKLCH;
}

/** Get CSS class set for a memory type */
export function memoryTypeClasses(type: string) {
  return MEMORY_TYPE_CLASSES[type] ?? { bg: "bg-muted", text: "text-muted-foreground", border: "border-border" };
}
