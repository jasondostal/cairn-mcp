/**
 * Memory relation type color registry.
 *
 * Used by memory-sheet, graph visualization, and memory detail pages.
 */

export const RELATION_CLASSES: Record<string, { text: string; border: string }> = {
  extends:      { text: "text-rel-extends",      border: "border-rel-extends" },
  contradicts:  { text: "text-rel-contradicts",  border: "border-rel-contradicts" },
  implements:   { text: "text-rel-implements",    border: "border-rel-implements" },
  depends_on:   { text: "text-rel-depends-on",   border: "border-rel-depends-on" },
  related:      { text: "text-muted-foreground",  border: "border-border" },
};

export const RELATION_OKLCH: Record<string, string> = {
  extends:     "oklch(0.55 0.20 264)",   // blue
  contradicts: "oklch(0.60 0.22 16)",    // red
  implements:  "oklch(0.65 0.17 162)",   // green
  depends_on:  "oklch(0.70 0.18 70)",    // amber
  related:     "oklch(0.55 0.04 264)",   // muted
};

export function relationColor(type: string): string {
  return RELATION_OKLCH[type] ?? RELATION_OKLCH.related;
}

export function relationClasses(type: string) {
  return RELATION_CLASSES[type] ?? RELATION_CLASSES.related;
}
