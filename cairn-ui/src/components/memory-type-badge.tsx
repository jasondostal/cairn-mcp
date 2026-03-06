import { Badge } from "@/components/ui/badge";
import { memoryTypeClasses } from "@/lib/colors";
import { isEphemeralType, ephemeralTypeClasses } from "@/lib/colors";

export function MemoryTypeBadge({ type }: { type: string }) {
  const colors = isEphemeralType(type) ? ephemeralTypeClasses(type) : memoryTypeClasses(type);

  return (
    <Badge variant="outline" className={`font-mono text-xs gap-1.5 ${colors.border}/40 ${colors.text}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${colors.bg}`} />
      {type}
    </Badge>
  );
}
