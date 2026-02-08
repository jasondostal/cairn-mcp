import { Star } from "lucide-react";

export function ImportanceBadge({ importance }: { importance: number }) {
  return (
    <div className="flex items-center gap-0.5">
      <Star className="h-3 w-3 text-muted-foreground" />
      <span className="font-mono text-xs text-muted-foreground">
        {importance.toFixed(2)}
      </span>
    </div>
  );
}
