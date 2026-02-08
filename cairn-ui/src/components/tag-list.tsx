import { Badge } from "@/components/ui/badge";
import { Tag } from "lucide-react";

export function TagList({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Tag className="h-3 w-3 text-muted-foreground" />
      {tags.map((t) => (
        <Badge key={t} variant="secondary" className="text-xs">
          {t}
        </Badge>
      ))}
    </div>
  );
}
