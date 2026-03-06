import { Badge } from "@/components/ui/badge";

const DOC_TYPE_HUES: Record<string, number> = {
  brief:   264,  // blue
  prd:     304,  // purple
  plan:    70,   // amber
  primer:  162,  // green
  writeup: 175,  // teal
  guide:   45,   // orange
};

export function DocTypeBadge({ type }: { type: string }) {
  const hue = DOC_TYPE_HUES[type];
  const color = hue != null ? `oklch(0.65 0.17 ${hue})` : undefined;

  return (
    <Badge
      variant="outline"
      className="font-mono text-xs gap-1.5"
      style={color ? {
        borderColor: `color-mix(in oklch, ${color} 40%, transparent)`,
        color,
      } : undefined}
    >
      {color && <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />}
      {type}
    </Badge>
  );
}
