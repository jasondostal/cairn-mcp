import { Badge } from "@/components/ui/badge";

export function MemoryTypeBadge({ type }: { type: string }) {
  return (
    <Badge variant="outline" className="font-mono text-xs">
      {type}
    </Badge>
  );
}
