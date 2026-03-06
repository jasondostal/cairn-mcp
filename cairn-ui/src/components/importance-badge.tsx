import { Star } from "lucide-react";
import { scoreColor } from "@/lib/colors";

export function ImportanceBadge({ importance }: { importance: number }) {
  const color = scoreColor(importance);
  return (
    <div className="flex items-center gap-0.5">
      <Star className="h-3 w-3" style={{ color }} />
      <span className="font-mono text-xs" style={{ color }}>
        {importance.toFixed(2)}
      </span>
    </div>
  );
}
