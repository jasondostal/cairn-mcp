/**
 * Ephemeral (working memory) type color registry.
 *
 * These are the decaying memory types: hypothesis, question, tension, etc.
 * Distinct from crystallized memory types (note, decision, rule...).
 */

export const EPHEMERAL_TYPE_CLASSES: Record<string, { text: string; bg: string; border: string }> = {
  hypothesis: { text: "text-eph-hypothesis", bg: "bg-eph-hypothesis", border: "border-eph-hypothesis" },
  question:   { text: "text-eph-question",   bg: "bg-eph-question",   border: "border-eph-question" },
  tension:    { text: "text-eph-tension",    bg: "bg-eph-tension",    border: "border-eph-tension" },
  connection: { text: "text-eph-connection", bg: "bg-eph-connection", border: "border-eph-connection" },
  thread:     { text: "text-eph-thread",     bg: "bg-eph-thread",     border: "border-eph-thread" },
  intuition:  { text: "text-eph-intuition",  bg: "bg-eph-intuition",  border: "border-eph-intuition" },
};

export const EPHEMERAL_TYPE_OKLCH: Record<string, string> = {
  hypothesis: "oklch(0.70 0.18 70)",    // amber — speculative
  question:   "oklch(0.60 0.24 304)",   // violet — inquiry
  tension:    "oklch(0.60 0.22 16)",    // red — conflict
  connection: "oklch(0.65 0.17 162)",   // teal — linking
  thread:     "oklch(0.55 0.20 264)",   // blue — continuity
  intuition:  "oklch(0.72 0.19 165)",   // mint — instinct
};

export const EPHEMERAL_TYPES = Object.keys(EPHEMERAL_TYPE_OKLCH);

export function ephemeralTypeColor(type: string): string {
  return EPHEMERAL_TYPE_OKLCH[type] ?? "oklch(0.55 0 0)";
}

export function ephemeralTypeClasses(type: string) {
  return EPHEMERAL_TYPE_CLASSES[type] ?? { text: "text-muted-foreground", bg: "bg-muted", border: "border-border" };
}

/** Check if a memory type is ephemeral */
export function isEphemeralType(type: string): boolean {
  return type in EPHEMERAL_TYPE_OKLCH;
}
