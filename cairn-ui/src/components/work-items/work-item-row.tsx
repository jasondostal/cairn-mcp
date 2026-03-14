"use client";

import { useState } from "react";
import type { WorkItem, WorkItemStatus, WorkspaceBackendInfo } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StatusDot, StatusText, PriorityLabel } from "./status-dot";
import { RiskTierBadge } from "./risk-tier-badge";
import { DispatchDialog } from "./dispatch-dialog";
import { ChevronRight, Hand, Bot, Activity } from "lucide-react";
import { ProjectPill } from "@/components/project-pill";

interface WorkItemRowProps {
  item: WorkItem;
  depth?: number;
  isLast?: boolean;
  showProject?: boolean;
  readyIds?: Set<number>;
  hasChildren?: boolean;
  isCollapsed?: boolean;
  isActive?: boolean;
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
  isActive = false,
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

  // Agent is actively working if heartbeat is within the last 2 minutes
  const isAgentWorking = item.agent_state === "working" && item.last_heartbeat
    && (Date.now() - new Date(item.last_heartbeat).getTime()) < 120_000;

  // Shared tree indent elements
  const treeIndent = depth > 0 ? (
    <>
      <span
        className="shrink-0 text-muted-foreground/60 font-mono text-xs select-none"
        style={{ width: `${(depth - 1) * 1.25}rem`, textAlign: "right" }}
      >
        {depth > 1 && <span style={{ marginRight: "0.25rem" }}>{" ".repeat((depth - 1) * 2)}</span>}
      </span>
      <span className="shrink-0 text-muted-foreground/60 font-mono text-xs select-none w-4">
        {isLast ? "└─" : "├─"}
      </span>
    </>
  ) : null;

  const collapseBtn = hasChildren ? (
    <button
      className="shrink-0 p-1 -m-0.5 rounded hover:bg-accent transition-transform"
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
  ) : null;

  const dispatchBtn = backends && backends.length > 0 && !isDone && !isCancelled && item.status !== "in_progress" ? (
    <>
      <button
        className="shrink-0 p-1 rounded text-muted-foreground/60 hover:text-muted-foreground hover:bg-accent transition-colors"
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
  ) : null;

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        (isDone || isCancelled) && "opacity-50",
        isActive && "bg-accent/30 ring-2 ring-primary/50",
      )}
      onClick={() => { if (!dispatchOpen) onClick?.(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (!dispatchOpen) onClick?.(); } }}
    >
      {/* Desktop: single row */}
      <div className="hidden md:flex items-center gap-2">
        {treeIndent}
        {collapseBtn}
        <StatusDot status={effectiveStatus} />
        <span className="font-mono text-xs text-muted-foreground shrink-0">{item.display_id}</span>
        {item.item_type === "epic" && (
          <span className="text-xs text-muted-foreground shrink-0">Epic:</span>
        )}
        <span className={cn("flex-1 truncate", isCancelled && "line-through")}>{item.title}</span>
        {isAgentWorking && (
          <span className="shrink-0 flex items-center gap-1 text-xs text-green-500" title="Agent working">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            <Activity className="h-3 w-3" />
          </span>
        )}
        {hasGate && <Hand className="h-3 w-3 text-status-gate shrink-0" />}
        <PriorityLabel priority={item.priority} />
        <RiskTierBadge tier={item.risk_tier} />
        {dispatchBtn}
        <StatusText status={effectiveStatus} />
        {item.assignee && (
          <span className="font-mono text-xs text-muted-foreground shrink-0">@{item.assignee}</span>
        )}
        {showProject && <ProjectPill name={item.project} />}
      </div>

      {/* Mobile: two-line layout — title gets full width */}
      <div className="md:hidden space-y-0.5">
        <div className="flex items-center gap-1.5">
          {treeIndent}
          {collapseBtn}
          <StatusDot status={effectiveStatus} />
          {item.item_type === "epic" && (
            <span className="text-xs text-muted-foreground shrink-0">Epic:</span>
          )}
          <span className={cn("flex-1 truncate", isCancelled && "line-through")}>{item.title}</span>
          {isAgentWorking && (
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
          )}
          {hasGate && <Hand className="h-3 w-3 text-status-gate shrink-0" />}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground pl-5">
          <span className="font-mono shrink-0">{item.display_id}</span>
          <PriorityLabel priority={item.priority} />
          <RiskTierBadge tier={item.risk_tier} />
          <StatusText status={effectiveStatus} />
          {item.assignee && <span className="font-mono shrink-0">@{item.assignee}</span>}
          {showProject && <ProjectPill name={item.project} />}
          {dispatchBtn}
        </div>
      </div>
    </div>
  );
}
