import type { ReactNode } from "react";
import { GripVertical, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DashboardWidgetProps {
  id: string;
  isEditing: boolean;
  onRemove: (id: string) => void;
  children: ReactNode;
}

export function DashboardWidget({
  id,
  isEditing,
  onRemove,
  children,
}: DashboardWidgetProps) {
  return (
    <div className={cn("group relative h-full", isEditing && "ring-1 ring-border/50 rounded-lg")}>
      {isEditing && (
        <>
          <div className="dashboard-drag-handle absolute top-1 left-1 z-10 cursor-grab rounded p-0.5 opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100 active:cursor-grabbing">
            <GripVertical className="h-4 w-4 text-muted-foreground" />
          </div>
          <button
            onClick={() => onRemove(id)}
            className="absolute top-1 right-1 z-10 rounded p-0.5 opacity-0 transition-opacity hover:bg-destructive/10 group-hover:opacity-100"
          >
            <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
          </button>
        </>
      )}
      <div className="h-full overflow-hidden">{children}</div>
    </div>
  );
}
