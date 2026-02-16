"use client";

import type { WorkItem, WorkItemStatus } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StatusDot, StatusText, PriorityDots } from "./status-dot";

interface WorkItemRowProps {
  item: WorkItem;
  depth?: number;
  isLast?: boolean;
  showProject?: boolean;
  readyIds?: Set<number>;
  onClick?: () => void;
}

export function WorkItemRow({
  item,
  depth = 0,
  isLast = false,
  showProject = false,
  readyIds,
  onClick,
}: WorkItemRowProps) {
  const isReady = readyIds?.has(item.id);
  const effectiveStatus: WorkItemStatus = isReady && (item.status === "open" || item.status === "ready")
    ? "ready"
    : item.status;
  const isDone = item.status === "done";
  const isCancelled = item.status === "cancelled";

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer",
        (isDone || isCancelled) && "opacity-50",
      )}
      onClick={onClick}
    >
      {/* Indentation with tree connectors */}
      {depth > 0 && (
        <span
          className="shrink-0 text-muted-foreground/40 font-mono text-xs select-none"
          style={{ width: `${(depth - 1) * 1.25}rem`, textAlign: "right" }}
        >
          {depth > 1 && <span style={{ marginRight: "0.25rem" }}>{" ".repeat((depth - 1) * 2)}</span>}
        </span>
      )}
      {depth > 0 && (
        <span className="shrink-0 text-muted-foreground/40 font-mono text-xs select-none w-4">
          {isLast ? "└─" : "├─"}
        </span>
      )}

      <StatusDot status={effectiveStatus} />

      <span className="font-mono text-xs text-muted-foreground shrink-0">
        {item.short_id}
      </span>

      {item.item_type === "epic" && (
        <span className="text-xs text-muted-foreground/70 shrink-0">Epic:</span>
      )}

      <span className={cn(
        "flex-1 truncate",
        isCancelled && "line-through",
      )}>
        {item.title}
      </span>

      <PriorityDots priority={item.priority} />

      <StatusText status={effectiveStatus} />

      {item.assignee && (
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          @{item.assignee}
        </span>
      )}

      {showProject && (
        <span className="font-mono text-xs text-muted-foreground/60 shrink-0">
          {item.project}
        </span>
      )}
    </div>
  );
}
