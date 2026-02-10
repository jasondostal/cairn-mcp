import { Badge } from "@/components/ui/badge";

const colors: Record<string, string> = {
  brief: "border-blue-500/50 text-blue-400",
  prd: "border-purple-500/50 text-purple-400",
  plan: "border-amber-500/50 text-amber-400",
  primer: "border-green-500/50 text-green-400",
  writeup: "border-teal-500/50 text-teal-400",
  guide: "border-orange-500/50 text-orange-400",
};

export function DocTypeBadge({ type }: { type: string }) {
  return (
    <Badge variant="outline" className={`font-mono text-xs ${colors[type] ?? ""}`}>
      {type}
    </Badge>
  );
}
