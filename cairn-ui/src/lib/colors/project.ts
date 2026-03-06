/**
 * Deterministic project color from name.
 *
 * Uses a hash-to-hue approach so every project gets a stable, unique-ish
 * color without needing a server-side palette. Extracted from memories/page.tsx
 * for cross-page reuse (work items, search, project list, etc.).
 */

/** Hash a project name to a hue angle (0-359) */
export function projectHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
  return ((h % 360) + 360) % 360;
}

/** Get an OKLCH color string for a project name */
export function projectColor(name: string): string {
  return `oklch(0.72 0.15 ${projectHue(name)})`;
}

/** Get a tinted background style object for project pills */
export function projectPillStyle(name: string): React.CSSProperties {
  const c = projectColor(name);
  return {
    backgroundColor: `color-mix(in oklch, ${c} 15%, transparent)`,
    borderColor: `color-mix(in oklch, ${c} 35%, transparent)`,
    border: "1px solid",
    color: c,
  };
}
