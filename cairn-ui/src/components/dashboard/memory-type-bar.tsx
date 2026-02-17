"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";

// OKLCH colors — saturated, perceptually distinct, dark-mode optimized
const TYPE_COLORS: Record<string, string> = {
  note: "oklch(0.55 0.2 264)",
  decision: "oklch(0.7 0.18 70)",
  rule: "oklch(0.6 0.22 16)",
  "code-snippet": "oklch(0.65 0.17 162)",
  learning: "oklch(0.6 0.24 304)",
  research: "oklch(0.6 0.15 200)",
  discussion: "oklch(0.65 0.18 45)",
  progress: "oklch(0.6 0.18 145)",
  task: "oklch(0.55 0.2 290)",
  debug: "oklch(0.65 0.2 30)",
  design: "oklch(0.55 0.18 250)",
};

const FALLBACK_COLOR = "oklch(0.45 0 0)";

function getColor(type: string): string {
  return TYPE_COLORS[type] ?? FALLBACK_COLOR;
}

interface Props {
  types: Record<string, number>;
}

export function MemoryTypeBar({ types }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);

  const sorted = Object.entries(types).sort(([, a], [, b]) => b - a);
  const total = sorted.reduce((sum, [, c]) => sum + c, 0);
  if (total === 0) return null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-muted-foreground">Memory Types</span>
          <span className="text-xs tabular-nums text-muted-foreground/60">{total} total</span>
        </div>

        {/* Proportional bar */}
        <div className="flex h-2 rounded-full overflow-hidden bg-muted">
          {sorted.map(([type, count]) => (
            <div
              key={type}
              className="h-full transition-opacity"
              style={{
                width: `${(count / total) * 100}%`,
                backgroundColor: getColor(type),
                opacity: hovered && hovered !== type ? 0.3 : 1,
              }}
              onMouseEnter={() => setHovered(type)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
          {sorted.map(([type, count]) => (
            <div
              key={type}
              className="flex items-center gap-1 cursor-default"
              onMouseEnter={() => setHovered(type)}
              onMouseLeave={() => setHovered(null)}
            >
              <span
                className="inline-block h-2 w-2 rounded-sm shrink-0"
                style={{ backgroundColor: getColor(type) }}
              />
              <span
                className={`text-[10px] tabular-nums transition-colors ${
                  hovered && hovered !== type
                    ? "text-muted-foreground/30"
                    : "text-muted-foreground"
                }`}
              >
                {type}{" "}
                <span className="font-mono">{count}</span>
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
