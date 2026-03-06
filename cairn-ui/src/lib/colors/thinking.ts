/**
 * Thinking thread thought-type colors.
 *
 * Used as border-left accents on thought cards in thinking/[id].
 * These are thought-level types (observation, hypothesis, reasoning...)
 * distinct from memory types (note, decision, rule...).
 */

const THOUGHT_TYPE_HUES: Record<string, number> = {
  observation:  264,  // blue
  hypothesis:   70,   // amber
  question:     304,  // purple
  reasoning:    200,  // cyan
  conclusion:   162,  // green
  alternative:  45,   // orange
  branch:       45,   // orange
  assumption:   16,   // rose
  analysis:     250,  // indigo
  insight:      85,   // yellow
  realization:  155,  // emerald
  pattern:      175,  // teal
  challenge:    25,   // red
  response:     264,  // slate-ish
};

/** Get OKLCH color string for a thought type (for inline styles) */
export function thoughtTypeColor(type: string): string | undefined {
  const hue = THOUGHT_TYPE_HUES[type];
  if (hue == null) return undefined;
  return `oklch(0.60 0.18 ${hue} / 50%)`;
}
