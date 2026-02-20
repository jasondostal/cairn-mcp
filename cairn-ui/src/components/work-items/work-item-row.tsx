"use client";

import { useState } from "react";
import type { WorkItem, WorkItemStatus, WorkspaceBackendInfo } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StatusDot, StatusText, PriorityLabel } from "./status-dot";
import { RiskTierBadge } from "./risk-tier-badge";
import { DispatchDialog } from "./dispatch-dialog";
import { ChevronRight, Hand, Bot } from "lucide-react";

interface WorkItemRowProps {
  item: WorkItem;
  depth?: number;
  isLast?: boolean;
  showProject?: boolean;
  readyIds?: Set<number>;
  hasChildren?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: (id: number) => void;
  onClick?: () => void;
  backends?: WorkspaceBackendInfo[];
  onDispatch?: () => void;
}

export function WorkItemRow({
  item,
  depth = 0,
  isLast = false,
  showProject = false,
  readyIds,
  hasChildren = false,
  isCollapsed = false,
  onToggleCollapse,
  onClick,
  backends,
  onDispatch,
}: WorkItemRowProps) {
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const isReady = readyIds?.has(item.id);
  const effectiveStatus: WorkItemStatus = isReady && (item.status === "open" || item.status === "ready")
    ? "ready"
    : item.status;
  const isDone = item.status === "done";
  const isCancelled = item.status === "cancelled";
  const hasGate = item.gate_type !== null && item.gate_type !== undefined;

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer",
        (isDone || isCancelled) && "opacity-50",
      )}
      onClick={() => { if (!dispatchOpen) onClick?.(); }}
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

      {/* Collapse chevron or spacer */}
      {hasChildren ? (
        <button
          className="shrink-0 p-0.5 -m-0.5 rounded hover:bg-accent transition-transform"
          onClick={(e) => {
            e.stopPropagation();
            onToggleCollapse?.(item.id);
          }}
          aria-label={isCollapsed ? "Expand" : "Collapse"}
        >
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 text-muted-foreground transition-transform",
              !isCollapsed && "rotate-90",
            )}
          />
        </button>
      ) : depth > 0 ? (
        <span className="shrink-0 w-[18px]" />
      ) : null}

      <StatusDot status={effectiveStatus} />

      <span className="font-mono text-xs text-muted-foreground shrink-0">
        {item.short_id}
      </span>

      {item.item_type === "epic" && (
        <span className="text-xs text-muted-foreground shrink-0">Epic:</span>
      )}

      <span className={cn(
        "flex-1 truncate",
        isCancelled && "line-through",
      )}>
        {item.title}
      </span>

      {hasGate && (
        <Hand className="h-3 w-3 text-[oklch(0.627_0.265_304)] shrink-0" />
      )}

      <PriorityLabel priority={item.priority} />
      <RiskTierBadge tier={item.risk_tier} />

      {backends && backends.length > 0 && !isDone && !isCancelled && item.status !== "in_progress" && (
        <>
          <button
            className="shrink-0 p-0.5 rounded text-muted-foreground/60 hover:text-muted-foreground hover:bg-accent transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              setDispatchOpen(true);
            }}
            title="Dispatch to agent"
            aria-label="Dispatch to agent"
          >
            <Bot className="h-3.5 w-3.5" />
          </button>
          <DispatchDialog
            open={dispatchOpen}
            onOpenChange={setDispatchOpen}
            item={item}
            backends={backends}
            onDispatched={onDispatch}
          />
        </>
      )}

      <StatusText status={effectiveStatus} />

      {item.assignee && (
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          @{item.assignee}
        </span>
      )}

      {showProject && (
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          {item.project}
        </span>
      )}
    </div>
  );
}
