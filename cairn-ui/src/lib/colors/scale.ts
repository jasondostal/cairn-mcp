/**
 * Continuous color scales for numeric values.
 *
 * These produce per-value OKLCH colors (not tokenizable) for things like
 * importance scores and salience levels.
 */

/** Score: low=cool muted lavender → high=warm vivid emerald */
export function scoreColor(value: number): string {
  const chroma = 0.04 + value * 0.20;
  const lightness = 0.50 + value * 0.24;
  const hue = 250 - value * 120;
  return `oklch(${lightness.toFixed(2)} ${chroma.toFixed(2)} ${hue.toFixed(0)})`;
}

/** Salience: low=muted peach → high=vivid amber */
export function salienceColor(value: number): string {
  const chroma = 0.04 + value * 0.20;
  const lightness = 0.50 + value * 0.28;
  const hue = 40 + value * 35;
  return `oklch(${lightness.toFixed(2)} ${chroma.toFixed(2)} ${hue.toFixed(0)})`;
}
